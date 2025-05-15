from django.db import migrations

def create_profiles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    UserProfile = apps.get_model('users', 'UserProfile')
    
    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user)

class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_userprofile_wallet'),  # Adjust this to your last migration
    ]
    
    operations = [
        migrations.RunPython(create_profiles),
    ] 