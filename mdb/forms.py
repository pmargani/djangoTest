from django import forms
from .models import Processing, Bank, Scan

class ProcessingStateForm(forms.Form):
    projectId = forms.CharField(label='Project ID')
    scanNum = forms.IntegerField(label='Scan Number', required=False)
    bank = forms.ModelChoiceField(queryset=Bank.objects.all(), label='Bank', required=False, empty_label='All Banks')
    processedState = forms.ChoiceField(label='Processing State', choices=Processing._meta.get_field('processedState').choices)

    def get_processing_objects(self):
        projectId = self.cleaned_data['projectId']
        scanNum = self.cleaned_data.get('scanNum')
        bank = self.cleaned_data.get('bank')
        if scanNum:
            scans = Scan.objects.filter(projectId=projectId, scanNum=scanNum)
        else:
            scans = Scan.objects.filter(projectId=projectId)
        if bank:
            return Processing.objects.filter(scan__in=scans, bank=bank)
        else:
            return Processing.objects.filter(scan__in=scans)
