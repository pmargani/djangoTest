from django.shortcuts import render

def landing_page(request):
    urls = [
        {"url": "/admin/", "name": "Admin", "desc": "Django admin site."},
        {"url": "/mdb/scans/", "name": "Scan List", "desc": "List all scans with filter."},
        {"url": "/mdb/set-processing-state/", "name": "Set Processing State", "desc": "Form to set processing state for processing objects."},
        {"url": "/mdb/mark-files-deleted/", "name": "Mark Files as Deleted", "desc": "Form to mark files as deleted by project, scan, and bank."},
    ]
    return render(request, "landing_page.html", {"urls": urls})
