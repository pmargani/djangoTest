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
