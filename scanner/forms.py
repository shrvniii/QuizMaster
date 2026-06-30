from django import forms
from .models import OMRSubmission
from participants.models import Participant

class OMRUploadForm(forms.ModelForm):
    class Meta:
        model = OMRSubmission
        fields = ['participant', 'image']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['participant'].required = False
        self.fields['participant'].help_text = "Optional. If left blank, the system will automatically read the roll number from the sheet."
        self.fields['participant'].widget.attrs.update({
            'class': 'form-control',
            'id': 'id_participant'
        })
        self.fields['image'].widget.attrs.update({
            'class': 'form-control',
            'accept': 'image/png, image/jpeg, image/jpg'
        })
        
        # Only show participants who do not have an OMR submission yet
        self.fields['participant'].queryset = Participant.objects.filter(omr_submission__isnull=True).order_by('roll_number')

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Validate file size (Max 10MB)
            if image.size > 10 * 1024 * 1024:
                raise forms.ValidationError("The uploaded file exceeds the 10 MB size limit.")
            
            # Validate MIME type / extension
            ext = image.name.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png']:
                raise forms.ValidationError("Only JPEG and PNG images are accepted.")
        return image
