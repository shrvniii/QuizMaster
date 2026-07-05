from django.shortcuts import render, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Count
from .models import School

class SchoolListView(LoginRequiredMixin, ListView):
    model = School
    template_name = 'schools/school_list.html'
    context_object_name = 'schools'

    def get_queryset(self):
        # Annotate each school with the count of participants
        return School.objects.annotate(participant_count=Count('participants')).order_by('code')

class SchoolCreateView(LoginRequiredMixin, CreateView):
    model = School
    fields = ['name', 'code']
    template_name = 'schools/school_form.html'
    success_url = reverse_lazy('schools:list')

    def form_valid(self, form):
        messages.success(self.request, f"School '{form.instance.name}' added successfully.")
        return super().form_valid(form)

class SchoolUpdateView(LoginRequiredMixin, UpdateView):
    model = School
    fields = ['name', 'code']
    template_name = 'schools/school_form.html'
    success_url = reverse_lazy('schools:list')

    def form_valid(self, form):
        messages.success(self.request, f"School '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

class SchoolDeleteView(LoginRequiredMixin, DeleteView):
    model = School
    template_name = 'schools/school_confirm_delete.html'
    success_url = reverse_lazy('schools:list')

    def form_valid(self, form):
        school = self.get_object()
        # Check if any participants are linked to this school
        if school.participants.exists():
            messages.error(self.request, f"Cannot delete '{school.name}' because it has registered participants.")
            return redirect('schools:list')
            
        messages.success(self.request, f"School '{school.name}' deleted successfully.")
        return super().form_valid(form)
