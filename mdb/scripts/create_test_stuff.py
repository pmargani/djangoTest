from datetime import timezone, datetime, timedelta

from mdb.models import Status, BankStatus, BankStatusX, Bank, Scan, File, Processing
from mdb.models import PROCESSED_ABORTED, PROCESSING_CYCSPEC
from utils import getDt





def create_test_stuff():

    bankA = Bank.objects.get(name='A')

    # for all scans
    projectId = 'AGBT22B_012_01'
    backend = 'VEGAS'
    receiver = 'Rcvr_2500'
    mode = 'coherent_fold'

    # first scan
    scanNum = 1
    now = datetime.now()
    utc = timezone.utc
    startTime = now.replace(tzinfo=utc)
    duration = 60
    endTime = startTime + timedelta(seconds=60)

    s = Scan(
        projectId=projectId,
        backend=backend,
        receiver=receiver,
        mode=mode,
        scanNum=scanNum,
        startTime=startTime,
        endTime=endTime,
        duration=duration
        )
    s.save()

    print("Created Scan: %s" % s)

    # make some files
    baseDir = "/mnt/ehd1/scratch"
    deviceDir = "VEGAS"
    fileType = 'raw'
    creationTime = startTime
    size = 4096

    names = [
      '59087_source_0001.0000.raw',
      '59087_source_0001.0001.raw',
      '59087_source_0001.0002.raw',
    ]

    for name in names:
        f = File(
            scan=s,
            bank=bankA,
            filename=name,
            baseDir=baseDir,
            deviceDir=deviceDir,
            fileType=fileType,
            size=size,
            creationTime=creationTime + timedelta(seconds=10)
        )
        f.save()
        print("Created File %s" % f)

    p = Processing(
        scan=s,
        bank=bankA,
        processingType=PROCESSING_CYCSPEC,
        processedState = PROCESSED_ABORTED,
        processStartTime = getDt(datetime(2022, 1, 1))
    )
    p.save()
    print("Created Processing %s " % p)

def run():
    # Bank.create_banks()
    # Status.create_singleton()
    # BankStatus.create_singletons()
    # BankStatusX.create_singletons()

    create_test_stuff()

# def main():
#     create_test_data()

# if __name__ == '__main__':
#     main()
