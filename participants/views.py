import csv
import io
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from .models import Participant
from .forms import ParticipantForm
from schools.models import School

class ParticipantListView(LoginRequiredMixin, ListView):
    model = Participant
    template_name = 'participants/participant_list.html'
    context_object_name = 'participants'
    paginate_by = 50

    def get_queryset(self):
        queryset = Participant.objects.select_related('school', 'omr_submission').order_by('roll_number')
        
        # Search
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(roll_number__icontains=q)
            
        # Filters
        school_id = self.request.GET.get('school', '')
        if school_id:
            queryset = queryset.filter(school_id=school_id)
            
        group = self.request.GET.get('group', '')
        if group:
            queryset = queryset.filter(group=group)
            
        paper_set = self.request.GET.get('set', '')
        if paper_set:
            queryset = queryset.filter(paper_set=paper_set)
            
        status = self.request.GET.get('status', '')
        if status:
            if status == 'PENDING':
                queryset = queryset.filter(omr_submission__isnull=True)
            else:
                queryset = queryset.filter(omr_submission__status=status)
                
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['schools'] = School.objects.all().order_by('code')
        # Preserve query parameters for pagination
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        context['query_params'] = query_params.urlencode()
        return context

class ParticipantUpdateView(LoginRequiredMixin, UpdateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'participants/participant_form.html'
    success_url = reverse_lazy('participants:list')

    def form_valid(self, form):
        messages.success(self.request, f"Participant '{form.instance.roll_number}' updated successfully.")
        return super().form_valid(form)

class ParticipantDeleteView(LoginRequiredMixin, DeleteView):
    model = Participant
    template_name = 'participants/participant_confirm_delete.html'
    success_url = reverse_lazy('participants:list')

    def form_valid(self, form):
        participant = self.get_object()
        if hasattr(participant, 'omr_submission'):
            messages.error(self.request, f"Cannot delete '{participant.roll_number}' because an OMR sheet has already been uploaded.")
            return redirect('participants:list')
            
        messages.success(self.request, f"Participant '{participant.roll_number}' deleted successfully.")
        return super().form_valid(form)

class ParticipantImportView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'participants/participant_import.html')

    def post(self, request):
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return render(request, 'participants/participant_import.html')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Invalid file format. Please upload a .csv file.")
            return render(request, 'participants/participant_import.html')

        try:
            # Read CSV
            file_data = csv_file.read().decode('utf-8')
            csv_data = io.StringIO(file_data)
            reader = csv.DictReader(csv_data)

            required_headers = ['roll_number', 'school_name', 'group', 'paper_set']
            headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
            
            # Check if all required headers are present
            missing_headers = [req for req in required_headers if req not in headers]
            if missing_headers:
                messages.error(
                    request, 
                    f"CSV is missing required columns: {', '.join(missing_headers)}. "
                    f"Ensure headers match the template exactly."
                )
                return render(request, 'participants/participant_import.html')

            success_count = 0
            error_rows = []
            row_num = 1  # 1-based index (header is row 1)

            # Process inside a transaction, but allow individual row failures 
            # so the user gets maximum feedback
            for row in reader:
                row_num += 1
                
                # Normalize keys to lowercase and strip whitespace
                row_data = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                
                roll_number = row_data.get('roll_number', '')
                school_name = row_data.get('school_name', '')
                group_raw = row_data.get('group', '').upper()
                set_raw = row_data.get('paper_set', '').upper()
                
                # Validation checks
                if not roll_number or not school_name:
                    error_rows.append(f"Row {row_num}: Roll Number and School Name are required.")
                    continue
                    
                # Validate roll number format (exactly 5 digits)
                if not roll_number.isdigit() or len(roll_number) != 5:
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): Roll number must be exactly 5 digits.")
                    continue
                    
                roll_school_code = roll_number[:2]
                roll_suffix = roll_number[2:]
                
                try:
                    suffix_val = int(roll_suffix)
                    if not (0 <= suffix_val <= 999):
                        error_rows.append(f"Row {row_num} (Roll {roll_number}): The last 3 digits of the roll number must be between 000 and 999.")
                        continue
                except ValueError:
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): The last 3 digits of the roll number must be numeric.")
                    continue                    
                # Map group (ignore spaces and underscores)
                group_clean = group_raw.replace(' ', '').replace('_', '')
                if 'JUNIOR' in group_clean:
                    group = 'JUNIOR'
                elif 'SENIOR' in group_clean:
                    group = 'SENIOR'
                else:
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): Invalid group '{group_raw}'. Must be 'Junior' or 'Senior'.")
                    continue
                    
                # Map paper set (ignore spaces and underscores)
                set_clean = set_raw.replace(' ', '').replace('_', '')
                if 'SETA' in set_clean or set_clean == 'A':
                    paper_set = 'SET_A'
                elif 'SETB' in set_clean or set_clean == 'B':
                    paper_set = 'SET_B'
                else:
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): Invalid paper set '{set_raw}'. Must be 'Set A', 'Set B', 'A', or 'B'.")
                    continue

                # Check if roll number already exists
                if Participant.objects.filter(roll_number=roll_number).exists():
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): Roll number already registered.")
                    continue

                try:
                    with transaction.atomic():
                        # Get or create school
                        school, created = School.objects.get_or_create(name=school_name)
                        if created:
                            # Assign the school code from the roll number
                            if School.objects.filter(code=roll_school_code).exists():
                                raise ValueError(f"School code '{roll_school_code}' is already assigned to another school.")
                            school.code = roll_school_code
                            school.save()
                        else:
                            # Verify that the school's code matches the roll number's prefix
                            if not school.code:
                                # Set it automatically if not set
                                if School.objects.filter(code=roll_school_code).exists():
                                    raise ValueError(f"School code '{roll_school_code}' is already assigned to another school.")
                                school.code = roll_school_code
                                school.save()
                            elif school.code != roll_school_code:
                                raise ValueError(f"School '{school_name}' already has code '{school.code}'. Roll number prefix '{roll_school_code}' does not match.")
                                
                        # Create participant
                        Participant.objects.create(
                            roll_number=roll_number,
                            school=school,
                            group=group,
                            paper_set=paper_set
                        )
                        success_count += 1
                except Exception as e:
                    error_rows.append(f"Row {row_num} (Roll {roll_number}): {str(e)}")

            # Report results
            if success_count > 0:
                messages.success(request, f"Successfully imported {success_count} students.")
            
            if error_rows:
                # Limit the number of displayed errors if it is huge
                max_display_errors = 10
                error_msg = f"Failed to import {len(error_rows)} rows:<br>" + "<br>".join(error_rows[:max_display_errors])
                if len(error_rows) > max_display_errors:
                    error_msg += f"<br>...and {len(error_rows) - max_display_errors} more errors."
                messages.warning(request, error_msg)
                
            return redirect('participants:list')

        except Exception as e:
            messages.error(request, f"Error reading CSV file: {str(e)}")
            return render(request, 'participants/participant_import.html')

class DownloadSampleCSVView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="bkj_oms_participants.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['roll_number', 'school_name', 'group', 'paper_set'])
        
        # 4 mock schools with codes: 01, 02, 03, 04
        schools = [
            ('St. Xavier School', '01'),
            ('Brighton Academy', '02'),
            ('Greenwood High', '03'),
            ('Oakridge School', '04')
        ]
        
        # We have 100 students. Let's distribute them.
        for school_idx, (school_name, school_code) in enumerate(schools):
            for student_idx in range(25):
                # 25 students per school = 100 total
                # Junior group: 0-499 suffix. Senior group: 500-999 suffix.
                if student_idx < 13:
                    # Junior
                    suffix = student_idx + 1 # 001 to 013
                    group = 'Junior'
                else:
                    # Senior
                    suffix = student_idx + 500 # 500 to 512
                    group = 'Senior'
                
                roll = f"{school_code}{suffix:03d}"  # e.g., "01001" or "01511"
                paper_set = 'Set A' if student_idx % 2 == 0 else 'Set B'
                
                writer.writerow([roll, school_name, group, paper_set])
            
        return response
