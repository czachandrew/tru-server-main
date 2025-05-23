import os
import logging
import zipfile
import paramiko
from typing import List, Dict, Generator
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from django_q.models import Schedule
from django.conf import settings
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 500
LOCAL_FILE = "synnex_products.zip"
REMOTE_FILE = "700601.zip"

class Command(BaseCommand):
    help = 'Download and process product data from Synnex SFTP server'

    def add_arguments(self, parser):
        parser.add_argument(
            '--local-only',
            action='store_true',
            help='Skip SFTP download and use existing local file',
        )
        parser.add_argument(
            '--remote-file',
            type=str,
            default=REMOTE_FILE,
            help='Name of the remote file to download.',
        )
        parser.add_argument(
            '--sftp-host',
            type=str,
            help='SFTP host address (overrides environment variable).',
        )
        parser.add_argument(
            '--sftp-username',
            type=str,
            help='SFTP username (overrides environment variable).',
        )
        parser.add_argument(
            '--sftp-password',
            type=str,
            help='SFTP password (overrides environment variable).',
        )

    def handle(self, *args, **options):
        # Check command line option first, then fall back to setting in settings.py
        local_only = options['local_only'] or getattr(settings, 'SYNNEX_LOCAL_ONLY', False)
        
        if not local_only:
            self.download_from_sftp(options['remote_file'], options['sftp_host'], options['sftp_username'], options['sftp_password'])
        else:
            self.stdout.write(self.style.WARNING("Using local file only (SFTP download skipped)"))
        
        if not os.path.exists(LOCAL_FILE):
            self.stdout.write(self.style.ERROR(f"File not found: {LOCAL_FILE}"))
            return
            
        self.process_file()

    def download_from_sftp(self, remote_file=None, host=None, username=None, password=None):
        """Download file from SFTP server"""
        # Get SFTP credentials from arguments or environment
        sftp_host = host or os.getenv("SFTP_HOST")
        sftp_username = username or os.getenv("SFTP_USERNAME")
        sftp_password = password or os.getenv("SFTP_PASSWORD")
        remote_file = remote_file or REMOTE_FILE
        
        if not all([sftp_host, sftp_username, sftp_password]):
            self.stdout.write(self.style.WARNING("Missing SFTP credentials - skipping download"))
            return False
            
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(sftp_host, username=sftp_username, password=sftp_password)
            
            with ssh.open_sftp() as sftp:
                sftp.get(remote_file, LOCAL_FILE)
                
            self.stdout.write(self.style.SUCCESS(f"Downloaded {remote_file} to {LOCAL_FILE}"))
            return True
        except paramiko.AuthenticationException:
            self.stdout.write(self.style.ERROR("SFTP Authentication failed"))
        except paramiko.SSHException as e:
            self.stdout.write(self.style.ERROR(f"SFTP Connection error: {str(e)}"))
        except IOError as e:
            self.stdout.write(self.style.ERROR(f"File transfer error: {str(e)}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Unexpected error during SFTP transfer: {str(e)}"))
        finally:
            ssh.close()
        return False
    
    def process_file(self):
        """Process the downloaded file"""
        file_size = os.path.getsize(LOCAL_FILE) / 1024
        self.stdout.write(f"Processing file. Size: {file_size:.2f}KB")
        
        data = []
        for row in self.read_zip_file(LOCAL_FILE):
            if (len(row) < 19 or row[18] != "Y" or 
                (len(row) > 22 and row[22] and row[22] != "RTL")):
                continue
                
            record = self.create_record(row)
            data.append(record)
        
        self.stdout.write(f"Found {len(data)} valid products")
        self.create_or_update_database_records(data)
    
    def read_zip_file(self, zip_file_path, delimiter="~", chunk_size=1024):
        """Read a zip file in chunks and yield rows"""
        with zipfile.ZipFile(zip_file_path, "r") as zfile:
            ap_file_name = zfile.namelist()[0]
            with zfile.open(ap_file_name, "r") as file:
                last_partial_line = ""
                while True:
                    data = file.read(chunk_size)
                    if not data:
                        break
                    data = last_partial_line + data.decode("utf-8", errors="replace")
                    lines = data.splitlines()
                    last_partial_line = lines.pop() if data[-1] != "\n" else ""
                    for line in lines:
                        yield line.split(delimiter)
                if last_partial_line:
                    yield last_partial_line.split(delimiter)
    
    def create_record(self, row):
        """Create a record from a row of data"""
        return {
            "name": f"{row[3]}({row[7]})",
            "mfr_part": row[3],
            "reseller_part": row[4],
            "status": row[5],
            "manufacturer": row[7],
            "description": row[6],
            "provider": "Synnex",
            "long_description": "".join(
                row[i] if len(row) > i else "" for i in range(49, 52)
            ),
            "qty": row[9],
            "product_weight": row[27],
            "product_height": row[54],
            "product_width": row[53],
            "product_length": row[52],
            "initial_price": row[12],
            "msrp": row[13],
            "synnex_category_code": row[24],
        }
    
    def create_or_update_database_records(self, data):
        """Process data in batches with Django-Q"""
        task_ids = []
        for i in range(0, len(data), BATCH_SIZE):
            batch = data[i:i+BATCH_SIZE]
            task_id = async_task("products.tasks.process_batch", batch)
            task_ids.append(task_id)
            self.stdout.write(f"Batch {i//BATCH_SIZE + 1}: Task ID {task_id}")
        
        # Add scheduled task to check completion and send email
        schedule = Schedule.objects.create(
            func="products.tasks.check_tasks_and_send_email",
            name="Check Import Tasks and Send Email",
            schedule_type=Schedule.MINUTES,
            args=task_ids,
            minutes=1,
            repeats=10,  # Check 10 times and stop
        )
        
        self.stdout.write(self.style.SUCCESS(f"Scheduled {len(task_ids)} batch tasks and follow-up check (Schedule ID: {schedule.id})")) 