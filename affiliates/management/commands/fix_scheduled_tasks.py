from django.core.management.base import BaseCommand
from django_q.models import Schedule
import json
import logging

logger = logging.getLogger('affiliate_tasks')

class Command(BaseCommand):
    help = 'Fix all scheduled tasks with incorrectly formatted arguments'

    def handle(self, *args, **options):
        # Get all scheduled tasks
        all_tasks = Schedule.objects.all()
        self.stdout.write(f"Examining {all_tasks.count()} scheduled tasks...")
        
        fixed_count = 0
        deleted_count = 0
        
        for task in all_tasks:
            try:
                # Try to parse the args as JSON
                json.loads(task.args)
                # If we get here, the args are valid JSON
                continue
            except (json.JSONDecodeError, TypeError):
                # Args are not valid JSON, try to fix
                original_args = task.args
                
                # For check_affiliate_link_status
                if task.func == 'affiliates.tasks.check_affiliate_link_status':
                    try:
                        # Parse comma-separated args
                        parts = original_args.split(',')
                        if len(parts) >= 2:
                            affiliate_link_id, task_id = parts[0], parts[1]
                            retry_count = int(parts[2]) if len(parts) > 2 else 0
                            
                            # Convert to proper JSON list
                            task.args = json.dumps([affiliate_link_id, task_id, retry_count])
                            task.save()
                            fixed_count += 1
                            self.stdout.write(f"Fixed check_affiliate_link_status task: {task.id}")
                            continue
                    except Exception as e:
                        self.stdout.write(f"Couldn't fix task {task.id}: {str(e)}")
                
                # For check_stalled_affiliate_task
                if task.func == 'affiliates.tasks.check_stalled_affiliate_task':
                    try:
                        # Convert single argument to JSON list
                        task_id = original_args
                        task.args = json.dumps([task_id])
                        task.save()
                        fixed_count += 1
                        self.stdout.write(f"Fixed check_stalled_affiliate_task task: {task.id}")
                        continue
                    except Exception as e:
                        self.stdout.write(f"Couldn't fix task {task.id}: {str(e)}")
                
                # If we can't fix it, delete it
                task_id = task.id
                task_func = task.func
                task.delete()
                deleted_count += 1
                self.stdout.write(f"Deleted unfixable task {task_id} ({task_func})")
        
        self.stdout.write(self.style.SUCCESS(
            f"Task cleanup complete: {fixed_count} fixed, {deleted_count} deleted"
        ))
        logger.info(f"Task cleanup complete: {fixed_count} fixed, {deleted_count} deleted") 