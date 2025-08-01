import os

from django.core.files.storage import FileSystemStorage
from django.db import models

from utils import isPidRunning, formatDt, getDt, getInternalMount


qualityCheckStorage = FileSystemStorage(location='/users/pmargani/tmp/qualityChecks')

# String Constants for processing type
PROCESSING_CYCSPEC = 'CYCSPEC'

# String constants for the Scan.processedState field
# TBF: perhaps use an enumeration table for these?
PROCESSED_NOT_STARTED = 'NOT_STARTED'
PROCESSED_STARTED = 'STARTED'
PROCESSED_COMPLETED = 'COMPLETED'
PROCESSED_ABORTED = 'ABORTED'
PROCESSED_FAILED = 'FAILED'

# ranking in terms of success
PROCESSED_STATES = [
    PROCESSED_COMPLETED,
    PROCESSED_NOT_STARTED,
    PROCESSED_STARTED,
    PROCESSED_ABORTED,
    PROCESSED_FAILED,
]

PROCESSED_STATES_CHOICES = [(s, s) for s in PROCESSED_STATES]

NUMBANKS = 3*8
BANKNAMES = [chr(ord('A')+i) for i in range(NUMBANKS)]

# Create your models here.
class Bank(models.Model):
    name = models.CharField(max_length=256)

    def __str__(self):
        return self.name

    @staticmethod
    def create_banks():
        "static method for creating all our needed Bank objects"
        for n in BANKNAMES:
            b, created = Bank.objects.get_or_create(name=n)
            if created:
                b.save()
            print("bank %s created? %s" % (b, created))



class Scan(models.Model):
    scanNum = models.IntegerField()
    projectId = models.CharField(max_length=256)
    startTime = models.DateTimeField('start time')
    endTime = models.DateTimeField('duration time', null=True)
    duration = models.IntegerField() # seconds
    backend = models.CharField(max_length=256)
    receiver = models.CharField(max_length=256)
    mode = models.CharField(max_length=256)
    source = models.CharField(max_length=256, null=True)
    cycspec = models.BooleanField(default=False)
    banks = models.ManyToManyField(Bank)

    def __str__(self):
        return "Scan %d, Project: %s, Start: %s, # Files: %d" % (self.scanNum,
                self.projectId,
                self.startTime,
                self.file_set.count())

    def processedState(self):
        "Try to represent the states of all the banks' processed data"
        p = set([p.processedState for p in self.processing_set.all()])
        if len(p) == 0:
            # actually unknown!
            return PROCESSED_NOT_STARTED
        elif len(p) == 1:
            # easy: all banks have the same state
            return list(p)[0]
        else:
            # more complicated.  return the 'worst' state
            p = list(p)
            idx = max([PROCESSED_STATES.index(s) for s in p])
            return PROCESSED_STATES[idx]

    def getBankProcessedState(self, bankName):
        ps = self.processing_set.filter(bank__name=bankName)
        if len(ps) == 0:
            # this scan doesn't have a process obj for this bank;
            # maybe it wasn't using this banks?
            return None
        if len(ps) > 1:
            logging.error("Scan should only have one processing obj per bank")
            return None
        # must just be one
        p = ps[0]
        return p.processedState

    def getEndTimeStr(self):
        return formatDt(self.endTime)

    def getStartTimeStr(self):
        return formatDt(self.startTime)

    def isProcessed(self):
        "short hand for seeing if the processing was successful"
        return self.processedState() == PROCESSED_COMPLETED

    def isDeleted(self):
        "We consider it deleted if ALL it's files have been deleted"
        return len([f for f in self.file_set.all() if f.deleted == False]) == 0

    def isCycSpecDeleted(self):
        "We consider it deleted if all it's raw files have been deleted"
        return len([f for f in self.file_set.all() if f.deleted == False and f.isCycSpec()]) == 0

    def bankNames(self):
        "returns A,B if those are the two banks"
        return ",".join([b.name for b in self.banks.all().order_by('name')])

    def hasCycspecFiles(self, bankName=None):
        fs = self.getCycspecFiles(bankName=bankName)
        return len(fs) > 0

    def getCycspecFiles(self, bankName=None):
        "shorthand for simple query with File.fileType"
        if bankName is None:
            return self.file_set.filter(fileType='raw').order_by('creationTime')
        else:
            #print("Getting cycspec files for bank ", bankName)
            return self.file_set.filter(fileType='raw', bank__name=bankName).order_by('creationTime')

    def getQualityChecks(self):
        "This is two levels deep, so we make a method for it"
        return QualityCheck.objects.filter(file__scan=self).order_by('file__bank__name', 'file__filename', 'dataBlock')

class File(models.Model):
    scan = models.ForeignKey(Scan, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    filename = models.CharField(max_length=512)
    baseDir = models.CharField(max_length=512)
    deviceDir = models.CharField(max_length=512)
    fileType = models.CharField(max_length=256)
    creationTime = models.DateTimeField('creation time')
    size = models.BigIntegerField() # bytes
    fileNum = models.IntegerField(null=True)
    done = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)

    def isCycSpec(self):
        "The raw file extension presumes this is for cyclic spectroscopy"
        return self.fileType == 'raw'

    def exists(self):
        "Does this file still leave where it says it does?"
        return os.path.isfile(self.getFullPath())

    def getFullPath(self):
        "Join attributes together to get an absolute path"
        bankName = self.bank.name if self.bank is not None else ''
        proj = self.scan.projectId if self.scan is not None else ""
        return os.path.join(self.baseDir, proj, self.deviceDir, bankName, self.filename)

    def getInternalPath(self):
        "How to find this file on the interal drive?"
        bankName = self.bank.name if self.bank is not None else ''
        proj = self.scan.projectId if self.scan is not None else ""
        baseDir = os.path.join(getInternalMount(), "scratch")
        return os.path.join(baseDir, proj, self.deviceDir, bankName, self.filename)

    def getCreationTimeStr(self):
        return formatDt(self.creationTime)

    def __str__(self):
        scanNum = self.scan.scanNum if self.scan is not None else -1
        return "File for scan %d: %s" % (scanNum, self.filename)

class QualityCheck(models.Model):
    file = models.ForeignKey(File, on_delete=models.CASCADE)
    plotFile = models.ImageField(storage=qualityCheckStorage)
    fileSize = models.BigIntegerField() # bytes
    checkTime = models.DateTimeField('check time')
    dataBlock = models.IntegerField()
    packetIndex = models.BigIntegerField()
    headerStr = models.TextField()
    done = models.BooleanField(default=False)

    def __str__(self):
        return "QualityCheck for file %s, dataBlock %d" % (self.file, self.dataBlock)

    def displayName(self):
        #return self.__str__()
        return "QC for proj %s, scan %s, bank %s, block %s" % (self.file.scan.projectId, self.file.scan.scanNum, self.file.bank.name, self.dataBlock)

    def getCheckTimeStr(self):
        return formatDt(self.checkTime)

    def getHdrValue(self, key):
        hdr = self.getHeaderDict()
        if hdr is None:
            print("Could not make header dict")
            return None
        if key not in hdr:
            print("Key '%s' not in header" % key)
            return None
        return hdr[key]

    def getHeaderDict(self):
        "Retrieve a specific value from the string rep. of the header"
        hdr = None
        if self.headerStr is None:
            return None
        try:
            hdr = eval(self.headerStr)
        except:
            print("Could not evaluate header as dictionary")
            return None
        return hdr




class Processing(models.Model):

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    processingType = models.CharField(max_length=256)
    processedState = models.CharField(max_length=256, choices=PROCESSED_STATES_CHOICES,
                                      default=PROCESSED_NOT_STARTED)
    processStartTime = models.DateTimeField('process start time', null=True)
    processEndTime = models.DateTimeField('process end time', null=True)
    details = models.TextField(null = True)
    pid = models.IntegerField(null = True)
    reprocess = models.BooleanField(default=False)

    def __str__(self):
        return "Processing bank %s for %s" % (self.bank, self.scan)

    def displayName(self):
        #return self.__str__()
        return "Processing for proj %s, scan %s, bank %s" % (self.scan.projectId, self.scan.scanNum, self.bank)

    def getProcessStartTimeStr(self):
        return formatDt(self.processStartTime)

    def getProcessEndTimeStr(self):
        return formatDt(self.processEndTime)

    def isProcessed(self):
        "short hand for seeing if the processing was successful"
        return self.processedState == PROCESSED_COMPLETED

    def isPidRunning(self):
        return isPidRunning(self.pid, self.bank.name)

class Status(models.Model):

    heartbeat = models.DateTimeField('should be updated with latest time', null=True)
    currentScanNum = models.IntegerField(null=True)
    currentProjectId = models.CharField(max_length=256, null=True)
    currentState = models.CharField(max_length=256, null=True)
    currentCycSpec = models.BooleanField(default=False)

    def getHeartbeatStr(self):
        return formatDt(self.heartbeat)

    @staticmethod
    def create_singleton():
        if Status.objects.count() == 0:
            s = Status()
            s.save()

class BankStatus(models.Model):

    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    processingHeartbeat = models.DateTimeField('heartbeat of processing daemon', null=True)
    processing = models.ForeignKey(Processing, on_delete=models.CASCADE, null=True)
    qualityCheckHeartbeat = models.DateTimeField('heartbeat of quality check daemon', null=True)
    qualityCheck = models.ForeignKey(QualityCheck, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return "BankStatus for Bank %s" % self.bank.name

    def getProcessingHeartbeatStr(self):
        return formatDt(self.processingHeartbeat)

    def getQualityCheckHeartbeatStr(self):
        return formatDt(self.qualityCheckHeartbeat)

    def isQualityCheckHeartbeatRecent(self):
        if self.qualityCheckHeartbeat is None:
            return False
        return (getDt() - self.qualityCheckHeartbeat).seconds < 60

    def isProcessingHeartbeatRecent(self):
        if self.processingHeartbeat is None:
            return False
        return (getDt() - self.processingHeartbeat).seconds < 60

    def hasQualityCheck(self):
        return self.qualityCheck is not None

    def hasQualityCheckStr(self):
        return "True" if self.hasQualityCheck() else "False"

    def qualityCheckId(self):
        return None if self.qualityCheck is None else self.qualityCheck.id

    def processingId(self):
        return None if self.processing is None else self.processing.id

    @staticmethod
    def create_singletons():
        for b in Bank.objects.all().order_by('name'):
            bs = BankStatus(bank=b)
            bs.save()

class BankStatusX(models.Model):

    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    processingHeartbeat = models.DateTimeField('heartbeat of processing daemon', null=True)
    processing = models.ForeignKey(Processing, on_delete=models.CASCADE, null=True)
    qualityCheckHeartbeat = models.DateTimeField('heartbeat of quality check daemon', null=True)
    qualityCheck = models.ForeignKey(QualityCheck, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return "BankStatus for Bank %s" % self.bank.name

    def displayName(self):
        return self.__str__()

    def getProcessingHeartbeatStr(self):
        return formatDt(self.processingHeartbeat)

    def getQualityCheckHeartbeatStr(self):
        return formatDt(self.qualityCheckHeartbeat)

    def isQualityCheckHeartbeatRecent(self):
        if self.qualityCheckHeartbeat is None:
            return False
        return (getDt() - self.qualityCheckHeartbeat).seconds < 60

    def isProcessingHeartbeatRecent(self):
        if self.processingHeartbeat is None:
            return False
        return (getDt() - self.processingHeartbeat).seconds < 60

    def hasQualityCheck(self):
        return self.qualityCheck is not None

    def hasQualityCheckStr(self):
        return "True" if self.hasQualityCheck() else "False"

    def qualityCheckId(self):
        return None if self.qualityCheck is None else self.qualityCheck.id

    def processingId(self):
        return None if self.processing is None else self.processing.id

    @staticmethod
    def create_singletons():
        for b in Bank.objects.all().order_by('name'):
            bs = BankStatusX(bank=b)
            bs.save()
