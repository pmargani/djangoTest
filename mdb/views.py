from .forms import MarkFilesDeletedForm
from .models import File
from django.contrib import messages
def mark_files_deleted(request):
    form = MarkFilesDeletedForm(request.POST or None)
    message = None
    warning = None
    if request.method == 'POST' and form.is_valid():
        scanNum = form.cleaned_data.get('scanNum')
        if not scanNum and not request.POST.get('confirm_all_scans'):
            warning = "This will mark all files in the project as deleted. Are you sure you want to continue?"
        else:
            files = form.get_files()
            updated_count = 0
            affected_projects = set()
            affected_scans = set()
            affected_banks = set()
            for f in files:
                f.deleted = True
                f.save()
                updated_count += 1
                if hasattr(f, 'scan') and f.scan:
                    affected_projects.add(f.scan.projectId)
                    affected_scans.add(f.scan.scanNum)
                if hasattr(f, 'bank') and f.bank:
                    affected_banks.add(f.bank.name)
            if updated_count == 0:
                message = { 'text': "No files matched", 'color': "red" }
            else:
                details = []
                if affected_projects:
                    details.append(f"Projects: {', '.join(str(p) for p in affected_projects)}")
                if affected_scans:
                    details.append(f"Scans: {', '.join(str(s) for s in affected_scans)}")
                if affected_banks:
                    details.append(f"Banks: {', '.join(str(b) for b in affected_banks)}")
                detail_str = "; ".join(details)
                messages.success(request, f"Marked {updated_count} files as deleted. {detail_str}")
    return render(request, 'mdb/mark_files_deleted.html', {'form': form, 'message': message, 'warning': warning})
from django.shortcuts import redirect
from .forms import ProcessingStateForm
def set_processing_state(request):
    form = ProcessingStateForm(request.POST or None)
    message = None
    warning = None
    if request.method == 'POST' and form.is_valid():
        scanNum = form.cleaned_data.get('scanNum')
        if not scanNum and not request.POST.get('confirm_all_scans'):
            warning = "This will set all scans in the project. Are you sure you want to continue?"
        else:
            processing_objs = form.get_processing_objects()
            new_state = form.cleaned_data['processedState']
            updated_count = 0
            for p in processing_objs:
                p.processedState = new_state
                p.save()
                updated_count += 1
            if updated_count == 0:
                message = { 'text': "No objects matched", 'color': "red" }
            else:
                message = { 'text': f"Updated {updated_count} processing objects.", 'color': "green" }
    return render(request, 'mdb/set_processing_state.html', {'form': form, 'message': message, 'warning': warning})
from .models import Processing
from django.views.generic import DetailView
class ProcessingDetailView(DetailView):
    model = Processing
    template_name = 'mdb/processing_detail.html'
    context_object_name = 'processing'
from django.views.generic import DetailView
from .models import Scan
class ScanDetailView(DetailView):
    model = Scan
    template_name = 'mdb/scan_detail.html'
    context_object_name = 'scan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scan = self.object
        context['files'] = scan.file_set.all()
        context['qualitychecks'] = getattr(scan, 'qualitycheck_set', None)
        if context['qualitychecks'] is not None:
            context['qualitychecks'] = scan.qualitycheck_set.all()
        else:
            context['qualitychecks'] = []
        context['processing'] = scan.processing_set.all()
        return context
from django.shortcuts import render
from django.views.generic import ListView
from .models import Scan

class ScanListView(ListView):
    model = Scan
    template_name = 'mdb/scan_list.html'
    context_object_name = 'scans'

    def get_queryset(self):
        queryset = super().get_queryset()
        # Example filter: filter by projectId if provided in GET params
        project_id = self.request.GET.get('projectId')
        if project_id:
            queryset = queryset.filter(projectId=project_id)
        return queryset
# Create your views here.
