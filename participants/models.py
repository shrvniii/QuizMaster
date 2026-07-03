from django.db import models
from schools.models import School

class Participant(models.Model):
    GROUP_CHOICES = [
        ('JUNIOR', 'Junior'),
        ('SENIOR', 'Senior'),
    ]
    
    SET_CHOICES = [
        ('SET_A', 'Set A'),
        ('SET_B', 'Set B'),
    ]

    roll_number = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='participants')
    group = models.CharField(max_length=10, choices=GROUP_CHOICES)
    paper_set = models.CharField(max_length=5, choices=SET_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        
        if not self.roll_number:
            return
            
        # 1. Roll number must be exactly 5 digits
        if not self.roll_number.isdigit() or len(self.roll_number) != 5:
            raise ValidationError({'roll_number': 'Roll number must be exactly 5 digits.'})
            
        # 2. Extract and validate school code
        if self.school:
            school_code = self.school.code
            roll_school_code = self.roll_number[:2]
            
            if not school_code:
                # Set the school code automatically if it's not set, and it's not already used
                if School.objects.filter(code=roll_school_code).exclude(pk=self.school.pk).exists():
                    raise ValidationError({
                        'roll_number': f"The school code '{roll_school_code}' (from the roll number) is already assigned to another school."
                    })
                self.school.code = roll_school_code
                self.school.save()
            else:
                # Check if it matches
                if school_code != roll_school_code:
                    raise ValidationError({
                        'roll_number': f"The first 2 digits of the roll number ('{roll_school_code}') must match the selected school's code '{school_code}'."
                    })
                    
        # 3. Validate unique number range based on group selection
        last_three_str = self.roll_number[2:]
        try:
            last_three_val = int(last_three_str)
            if self.group == 'JUNIOR':
                if not (0 <= last_three_val <= 499):
                    raise ValidationError({
                        'roll_number': "For JUNIOR group, the last 3 digits of the roll number must be between '000' and '499'."
                    })
            elif self.group == 'SENIOR':
                if not (500 <= last_three_val <= 999):
                    raise ValidationError({
                        'roll_number': "For SENIOR group, the last 3 digits of the roll number must be between '500' and '999'."
                    })
        except ValueError:
            raise ValidationError({'roll_number': 'The last 3 digits of the roll number must be numeric.'})

    def __str__(self):
        return f"{self.roll_number} - {self.full_name}"

