from django import forms
from .models import Quote

class QuoteUploadForm(forms.ModelForm):
    """Simple form for testing quote uploads"""
    
    demo_mode = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Enable demo mode for superior pricing on unmatched products"
    )
    
    class Meta:
        model = Quote
        fields = ['pdf_file', 'vendor_name', 'vendor_company', 'demo_mode']
        widgets = {
            'pdf_file': forms.FileInput(attrs={
                'accept': '.pdf',
                'class': 'form-control'
            }),
            'vendor_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional: Contact person name'
            }),
            'vendor_company': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Optional: Company name hint'
            })
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pdf_file'].help_text = "Upload a PDF quote (max 10MB)"
