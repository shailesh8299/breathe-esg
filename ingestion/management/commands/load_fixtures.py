from django.core.management.base import BaseCommand
from django.core.management import call_command
from ingestion.models import PlantLookup, MaterialLookup

class Command(BaseCommand):
    help = 'Loads initial_lookups.json fixture and prints loaded record counts'

    def handle(self, *args, **options):
        self.stdout.write("Loading initial_lookups.json...")
        call_command('loaddata', 'initial_lookups.json')
        
        plant_count = PlantLookup.objects.count()
        material_count = MaterialLookup.objects.count()
        
        self.stdout.write(self.style.SUCCESS(
            f"Successfully loaded initial_lookups.json:\n"
            f"- PlantLookup records loaded: {plant_count}\n"
            f"- MaterialLookup records loaded: {material_count}"
        ))
