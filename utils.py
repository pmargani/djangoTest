import glob
import os
import shlex
import subprocess
import configparser
from multiprocessing import Pool
from datetime import datetime, timezone

from fabric import Connection

from djangoTest import settings

import logging


# pulsar mode names are confusing, but spectral line
# mode names are just 1 through 29
SL_MODES = ['MODE%d' % i for i in range(1,30)]

# we need to know the low bandwitch coherent modes
# because bank A is not taking data, so should be ignored
# TBF: read this from the config file, rather then hardcode:
bws = ['0064', '0128', '0256', '0512', '1024']
LBW_MODES = ['MODEc0100x%s' % bw for bw in bws]
LBW_MODES.extend(['MODEc0200x%s' % bw for bw in bws])

DSPSR_EXE = 'dspsr.12Jul2022'

def detectCSProcessing(banks):
    "Is CS processing going on on any of the banks?"
    # TBF: how to make this faster?
    # for bank in Bank.objects.all().order_by('name'):
    #     host = getBankHost(bank.name)
    #     pid = isProgramRunning(host, 'dspsr.12Jul2022')
    #     p = None
    #     if pid is not None:
    #         logging.info()
    hosts = getBankHosts(banks)
    with Pool(processes=len(banks)) as pool:
        csPids = pool.map(isDspsrRunning, hosts)
    return not all([pid is None for pid in csPids])


def getBankHosts(banks):
    "Return the host names for Banks A, B, ..."
    #return [getBankHost(b.name) for b in Bank.objects.all().order_by('name')]
    return [getBankHost(b) for b in banks] #Bank.objects.all().order_by('name')]

#def getProcessingPidInfo(host):
#    pid = isDspsrRunning(host)
#    p = None
    #if pid is not None:
    #    try:
    #        p = Process.objects.get(pid = pid)
    #    except:
    #        p = None
    #        print("Could not find pid in DB: %s" % pid)
#    print("dspsr running on host %s as %s" % (host, pid))
#    return (bank.name, host, pid)

def getProcessingPids(banks):
    "Return info about CS processes running on Banks, if any"
    # dspsrPids = []
    # for bank in Bank.objects.all().order_by('name'):
    #     host = getBankHost(bank.name)
    #     pid = isProgramRunning(host, DSPSR_EXE)
    #     p = None
    #     if pid is not None:
    #         try:
    #             p = Process.objects.get(pid = pid)
    #         except:
    #             p = None
    #             print("Could not find pid in DB: %s" % pid)
    #     print("dspsr running on host %s as %s" % (host, pid))
    #     dspsrPids.append((bank.name, host, pid, p))
    # return dspsrPids
    hosts = getBankHosts(banks)
    with Pool(processes=len(banks)) as pool:
        pids = pool.map(isDspsrRunning, hosts)
    return pids

def parseDiskUsageStr(usageStr, cmd, path):
    """
    Parse the return from 'df path -H':
    'vegas-hpc13:/mnt/cycspec   72T  2.7T   70T   4% /home/cycspec-hpc13'
    Returns tuple of Size(T), Usage(T), Available(T), percent used.
    """
    result = (None, None, None, None)
    # should now look like:
    # 'vegas-hpc13:/mnt/cycspec   72T  2.7T   70T   4% /home/cycspec-hpc13'
    # try to parse the string
    outs = usageStr.split('\n')
    # we expect two lines of text, plus a third black char
    if len(outs) != 3:
        logging.error("1. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
        return result
    l = outs[1]
    if path not in l:
        logging.error("2. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
        return result
    ls = l.split(" ")
    if ls[-1] != path:
        logging.error("3. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
        return result
    # get the percentage
    try:
        percent = float(ls[-2][:-1])
    except:
        logging.error("3. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
        return result
    # get the size and usage
    # TBF: must be a better way to do this
    i = -3
    #while ls[i] == '' and abs(i) < len(ls):
    #    i -= 1
    nums = []
    for i in range(3, len(ls)):
        lsi = ls[-i]
        if lsi != '' and 'T' in lsi:
            try:
                n = float(lsi[:-1])
                nums.append(n)
            except:
                logging.error("4. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
                return (None, None, None, percent)
        if len(nums) >= 3:
            # we've got it all
            break
    if len(nums) != 3:
        logging.error("5. cmd %s failed with unexpected output: %s" % (cmd, usageStr))
        return (None, None, None, percent)

    # since we read from the end of the string towards the beginning
    nums.reverse()
    return (nums[0], nums[1], nums[2], percent)

def getDiskUsage(path):
    "Use call to 'df' to check on disk usage"
    result = (None, None, None, None)
    cmds = ["df", path, "-H"]
    cmd = " ".join(cmds)
    s = subprocess.run(cmds, capture_output=True)
    if s.returncode != 0:
        logging.error("cmd %s failed with error code: %d" % (cmd, s.returncode))
        return result
    # figure out what it is from the stdout
    try:
        out = s.stdout.decode('UTF-8')
    except:
        logging.error("cmd %s failed to produce sensible output" % cmd)
        return  result
    return parseDiskUsageStr(out, cmd, path)

def isLBWMode(mode):
    return mode in LBW_MODES

def isCoherentMode(mode):
    "MODEi1024x1024 -> 'i' is incoherent, 'c' for coherent"
    if not isNotSpectralLineMode(mode):
        return False # not even pulsar!
    return mode[4] == 'c'

def getVegasSubDir(mode):
    return 'VEGAS_CODD' if isCoherentMode(mode) else 'VEGAS'

def isNotSpectralLineMode(mode):
    return mode not in SL_MODES

def parsePulsarFilename(filename, fitsType):
    assert fitsType in ['fits', 'raw']

    if fitsType == 'fits':
        return parsePulsarFitsFilename(filename)
    else:
        return parsePulsarRawFilename(filename)

def parsePulsarFitsFilename(filename):
    """
    Parse names like:
       * vegas_59956_65259_J0340+4130_0004_0001.fits
       * vegas_59956_48356_CAL_0011_cal_0001.fits
    To get the:
       * extension
       * scan number
       * file number

    Pattern seems to be: vegasJ_(time)_(stamp)_(source)_(scan)[_cal_]_(filenum).(extension)
    """

    # first see if this is a 'cal' scan
    extOffset = -4
    calOffset = -13
    scanIdx = 4
    if 'cal' in filename and filename[calOffset:calOffset+3] == 'cal':
        fileNumIdx = scanIdx + 2
    else:
        fileNumIdx = scanIdx + 1

    thisScanNum = int(filename.split('_')[scanIdx])
    fileNum = filename.split('_')[fileNumIdx]
    thisFileNum = int(fileNum.split('.')[0])

    return thisScanNum, thisFileNum

def parsePulsarRawFilename(filename):
    """
    Parse names like:
       * vegas_59956_65259_J0340+4130_0004.0000.raw
    To get the:
       * extension
       * scan number
       * file number

    Pattern seems to be: vegasJ_(time)_(stamp)_(source)_(scan).(filenum).(extension)
    """

    # first see if this is a 'cal' scan
    extOffset = -3
    scanIdx = 4

    # f = 'vegas_59870_72107_none_0084.0000.raw'
    end = filename.split('_')[scanIdx]
    # end = '0084.0000.raw'
    thisScanNum = int(end.split('.')[0])
    thisFileNum = int(end.split('.')[1])

    return thisScanNum, thisFileNum

def getDt(dt=None):
    "Make sure the datetime obj is tz-aware w/ UTC"
    if dt is None:
        dt = datetime.now()
    utc = timezone.utc
    return dt.replace(tzinfo=utc)

def formatDt( dt, frmt=None):
    "Convenience fnc for getting datetime to string"
    if dt is None:
        return None
    if frmt is None:
        frmt = '%Y-%m-%d %H:%M:%S'
    return dt.strftime(frmt)

# we have code everywhere for reading YGOR config files,
# but not in this repo!
def getConfigValue(ygorDir, configFile, key):
    "Extract a value from a file 'configFile' in a dir 'ygorDir' that has 'key' := 'value'"
    fn = os.path.join(ygorDir, configFile)
    with open(fn, 'r') as f:
        ls = f.readlines()
    # get any values for the given key
    values = []
    for l in ls:
        if "#" == l[0]:
            # skip comments
            continue
        if ":=" not in l:
            # skip these too
            continue
        ll = l.split(":=")
        thisKey = ll[0].strip()
        if key == thisKey:
            # here's one value for the key we're looking for
            values.append(ll[1])
    if len(values) != 1:
        logging.error("Expected just one occurence of %s, found %d" % (key, len(values)))
        return None
    else:
        return values[0]

def readConfig(guppiConfigFile=None, ygorPath=None):
    "For reading a standard python config"
    if ygorPath is None:
        YT = 'YGOR_TELESCOPE'
        if YT in os.environ:
            ygorPath = os.environ[YT]
        else:
            ygorPath = "/home/gbt"

    if guppiConfigFile is None:
        guppiConfigFile = 'cycspec.conf'
    filePath = os.path.join(ygorPath, 'etc/config', guppiConfigFile)
    if not os.path.isfile(filePath):
        logging.error("Could not find config file: %s" % filePath)
        return None
    c = configparser.ConfigParser()
    c.read(filePath)
    return c

def getExternalMounts(filename=None, ygorPath=None):
    c = readConfig(guppiConfigFile=filename, ygorPath=ygorPath)
    return c['ExternalMounts']

def getInternalMount(filename=None, ygorPath=None):
    c = readConfig(guppiConfigFile=filename, ygorPath=ygorPath)
    return c['DEFAULT']['INTERNAL_MOUNT']

def getCycSpecFromConfig(ygorPath=None):
    c = readConfig(ygorPath=ygorPath)
    return c['DEFAULT']['CYCSPEC']

def isCycSpecSet(ygorPath=None):
    return getCycSpecFromConfig(ygorPath=ygorPath) == '1'

def getProcessingEnabledFromConfig(ygorPath=None):
    c = readConfig(ygorPath=ygorPath)
    return c['DEFAULT']['CYCSPEC_PROCESSING_ENABLED']

def isProcessingEnabled(ygorPath=None):
    return getProcessingEnabledFromConfig(ygorPath=ygorPath) == '1'

def getChalicePortFromConfig(ygorPath=None):
    c = readConfig(ygorPath=ygorPath)
    return int(c['DEFAULT']['CHALICEPORT'])

def getVegasDataDirFromConfig(ygorPath=None):
    c = readConfig(ygorPath=ygorPath)
    return c['DEFAULT']['VEGAS_DATA_DIR']

def processScanWithDspsr(
    gpuDevice, # -cuda
    cpu, # -cpu
    ncyc, # -cyclie
    parFile, # -E
    npols, # -d
    nphaseBins, # -b
    integration, # -L
    filePattern,
    scanNum,
    outputDir,
    bankName,
    obsMode=None,
    processValue=None,
    processingObj=None,
    test=None):

    if test is None:
        test = False

    logging.info("processing scan with dspsr: %s , obsMode: %s" % (scanNum, obsMode))

    #cmd = "source /home/cycspec/cycspec.bash; /home/sandboxes/jbrandt/dspsr/Signal/Pulsar/dspsr  -cuda 1,1 -cpu 22,23 -cyclic 128 -E /users/rlynch/CycSpec/B1937+21.basic.par -d 2 -b 512 -L 10 -O foo -a PSRFITS -e fits -v -O %s/CS%d %s*" % (outputDir, scanNum, filePattern)
    #cmd = "sleep 10"
    #os.system(cmd)
    #cmd = "/home/sandboxes/pmargani/count"

    # the above cmd line for dspr is more easily executed from a
    # local bash script
    # TBF: hard coded path!
    # cmd = "/home/sandboxes/pmargani/vpmmdb/vpmmdb/runDspsr %s %d %s" % (outputDir, scanNum, filePattern)
    runDspsr = os.path.join(settings.BASE_DIR, "runDspsr")

    # example:
    #cmd="/home/sandboxes/jbrandt/dspsr/Signal/Pulsar/dspsr  -cuda 1,1 -cpu 22,23 -cyclic 128 -E /users/rlynch/CycSpec/B1937+21.basic.par -d 2 -b 512 -L 10 -O foo -a PSRFITS -e fits -v -O $1/CS$2 $3*"
    # cmd = "%s %s %d %s" % (runDspsr, outputDir, scanNum, filePattern)
    # cmd = "%s %d %d %d %s %d %d %d %s %d %s" % (runDspsr,
    dspsr = "/home/cycspec/bin/dspsr.12Jul2022"
    args = {
        "-cuda": gpuDevice,
        "-cpu": cpu,
        "-cyclic": ncyc,
        "-d": npols,
        "-b": nphaseBins,
        "-L": integration,
        "-a": "PSRFITS",
        "-e": "fits" ,
        "-O": "%s/CS%s%s" % (outputDir, bankName, scanNum),
    }
    if obsMode is None:
        args["-E"] = parFile
    else:
        if 'cal' in obsMode or 'CAL' in obsMode:
            # cal obs modes don't use a parfile!
            # use instead: -c 0.04 -p 0 -cepoch <MJD>
            args["-c"] = 0.04
            args["-p"] = 0
            args["-D"] = 0
            args["-cepoch"] = 60000
        else:
            args["-E"] = parFile
    argStr = " ".join(["%s %s" % (k, v) for k, v in args.items()])
    cmd = "%s %s -v %s %s*" % (runDspsr, dspsr, argStr, filePattern)
    #cmdOld = "%s %s %s %s %s %s %s %s %s %s %s" % (runDspsr,
    #                                            gpuDevice,
    #                                            cpu,
    #                                            ncyc,
    #                                            parFile,
    #                                            npols,
    #                                            nphaseBins,
    #                                            integration,
    #                                            filePattern,
    #                                            scanNum,
    #                                            outputDir)

    logging.info("dspsr cmd: %s" % cmd)
    #if processingObj:
    #    processingObj.details = " Processing with: %s" % cmd
    #    processingObj.save()
    pid = None
    if not test:
        args = shlex.split(cmd)
        p = subprocess.Popen(args)
        pid = p.pid
        # pass on the pid to other stuff
        logging.info("Dspsr process pid: %s" % p.pid)
        if processValue is not None:
            processValue.value = p.pid
        #if processingObj:
        #    processingObj.pid = p.pid
        #    processingObj.save()

        #p.wait()
    else:
        logging.info("testing!  Not calling above cmd")
        return True

    #logging.info("Finished dspsr!")

    # TBF: check if dprocessed files are there
    #outfiles = os.listdir(outputDir)
    #outfiles = [f for f in outfiles if "CS%s%d" % (bankName, scanNum) in f]

    #logging.info("Produced # output files in %s: %d" % (outputDir, len(outfiles)))

    #return len(outfiles) > 1, cmd, pid

def startProcessingWithDspsr(
    gpuDevice, # -cuda
    cpu, # -cpu
    ncyc, # -cyclie
    parFile, # -E
    npols, # -d
    nphaseBins, # -b
    integration, # -L
    filePattern,
    scanNum,
    outputDir,
    bankName,
    obsMode=None,
    processValue=None,
    processingObj=None,
    test=None):

    if test is None:
        test = False

    logging.info("processing scan with dspsr: %s " % scanNum)

    #cmd = "source /home/cycspec/cycspec.bash; /home/sandboxes/jbrandt/dspsr/Signal/Pulsar/dspsr  -cuda 1,1 -cpu 22,23 -cyclic 128 -E /users/rlynch/CycSpec/B1937+21.basic.par -d 2 -b 512 -L 10 -O foo -a PSRFITS -e fits -v -O %s/CS%d %s*" % (outputDir, scanNum, filePattern)
    #cmd = "sleep 10"
    #os.system(cmd)
    #cmd = "/home/sandboxes/pmargani/count"

    # the above cmd line for dspr is more easily executed from a
    # local bash script
    # TBF: hard coded path!
    # cmd = "/home/sandboxes/pmargani/vpmmdb/vpmmdb/runDspsr %s %d %s" % (outputDir, scanNum, filePattern)
    runDspsr = os.path.join(settings.BASE_DIR, "runDspsr")

    # example:
    #cmd="/home/sandboxes/jbrandt/dspsr/Signal/Pulsar/dspsr  -cuda 1,1 -cpu 22,23 -cyclic 128 -E /users/rlynch/CycSpec/B1937+21.basic.par -d 2 -b 512 -L 10 -O foo -a PSRFITS -e fits -v -O $1/CS$2 $3*"
    # cmd = "%s %s %d %s" % (runDspsr, outputDir, scanNum, filePattern)
    # cmd = "%s %d %d %d %s %d %d %d %s %d %s" % (runDspsr,
    dspsr = "/home/cycspec/bin/dspsr.12Jul2022"
    args = {
        "-cuda": gpuDevice,
        "-cpu": cpu,
        "-cyclic": ncyc,
        "-d": npols,
        "-b": nphaseBins,
        "-L": integration,
        "-a": "PSRFITS",
        "-e": "fits" ,
        "-O": "%s/CS%s%s" % (outputDir, bankName, scanNum),
    }
    if obsMode is None:
        args["-E"] = parFile
    else:
        if 'cal' in obsMode or 'CAL' in obsMode:
            # cal obs modes don't use a parfile!
            # use instead: -c 0.04 -p 0 -cepoch <MJD>
            args["-c"] = 0.04
            args["-p"] = 0
            args["-D"] = 0
            args["-cepoch"] = 60000
        else:
            args["-E"] = parFile
    argStr = " ".join(["%s %s" % (k, v) for k, v in args.items()])
    cmd = "%s %s -v %s %s*" % (runDspsr, dspsr, argStr, filePattern)
    #cmdOld = "%s %s %s %s %s %s %s %s %s %s %s" % (runDspsr,
    #                                            gpuDevice,
    #                                            cpu,
    #                                            ncyc,
    #                                            parFile,
    #                                            npols,
    #                                            nphaseBins,
    #                                            integration,
    #                                            filePattern,
    #                                            scanNum,
    #                                            outputDir)

    logging.info("dspsr cmd: %s" % cmd)
    #if processingObj:
    #    processingObj.details = " Processing with: %s" % cmd
    #    processingObj.save()
    # pid = None
    #oif not test:
    if test:
        cmd = 'sleep 5'
    if 1:
        args = shlex.split(cmd)
        p = subprocess.Popen(args)
        # pid = p.pid
        # pass on the pid to other stuff
        logging.info("Dspsr process pid: %s" % p.pid)
        # if processValue is not None:
            # processValue.value = p.pid
        #if processingObj:
        #    processingObj.pid = p.pid
        #    processingObj.save()

        #p.wait()
    else:
        logging.info("testing!  Not calling above cmd")


    return p, cmd

    #logging.info("Finished dspsr!")

    # TBF: check if dprocessed files are there
    #outfiles = os.listdir(outputDir)
    #outfiles = [f for f in outfiles if "CS%s%d" % (bankName, scanNum) in f]

    #logging.info("Produced # output files in %s: %d" % (outputDir, len(outfiles)))

    #return len(outfiles) > 1, cmd, pid

def getBankHost(bankName):
    "From system.conf, 'A' -> 'vegas-hpc11'"

    # assert bankName is legal

    # 'A' -> entry in system.conf
    entry = "VegasBank%sHost" % bankName
    return getSystemHost(entry)

def getSystemHost(entry):
    "Get the host name of something in system.conf"
    ygorDir = os.path.join(settings.YGOR_TELESCOPE, 'etc/config')
    host = getConfigValue(ygorDir, "system.conf", entry)
    # remove whitespace and quotes from
    # ' "vegas-hpc11"\n'
    host = host.strip()
    return host[1:-1]

def isDspsrRunning(host):
    "Returns pid of dspsr found running on given host"
    return isProgramRunning(host, DSPSR_EXE)

def isProgramRunning(host, program):
    "Returns pid of given program found running on given host"

    #cmd = "ps -ef | grep %s | grep -v grep"
    cmd = "/sbin/pidof %s" % program

    result = Connection(host).run(cmd, hide=False, warn=True)
    # we can get more details from result.stdout, stderr ...
    if result.exited == 0:
        # try to find the PID!
        logging.info("pidof worked")
        print("pidof worked")
        r = result.stdout
        pids = r.split(' ')
        if len(pids) > 1:
            # too many!
            logging.error("Too many PIDs for %s: %s" % (program, pids))
            print("Too many PIDs for %s: %s" % (program, pids))
            return None
        else:
            try:
                pid = int(r)
            except:
                pid = None
                logging.error("Could not convert PID: %s" % r)
                print("Could not convert PID: %s" % r)
            return pid
    else:
        # program not running
        print("pidof didn't find anything")
        logging.info("pidof didn't find anything")
        return None


def isPidRunning(pid, bankName):
    "Find out if the given pid is running on this bank's host"

    if pid is None:
        return False

    hostName = getBankHost(bankName)

    # look for the PID, removing grep from the results
    # cmd = "ps -ef | grep %d | grep -v grep" % pid

    # here's another way of seeing if pid is running
    cmd = "ls /proc/%d" % pid

    # it seems that if the PID is not found, using the
    # grep -v grep causes an error
    # so will using the proc dir if pid is not running

    result = Connection(hostName).run(cmd, hide=False, warn=True)
    # we can get more details from result.stdout, stderr ...
    return result.exited == 0

def getDtFromLogName(logName):
    "path/process.pid.timestamp -> datetime"
    fn = os.path.basename(logName)
    # ex: cycspecProcessIdle.d.33802.2022_11_09_15:14:06
    ts = fn.split('.')[-1]
    frmt = "%Y_%m_%d_%H:%M:%S"
    dt = datetime.strptime(ts, frmt)
    utc = timezone.utc
    return dt.replace(tzinfo=utc)

def getDtFromLogLine(ln):
    "Return Datetime obj of timestamp at beginning of log line"
    # well, does it have a timestamp?  the logging we've
    # done so far always has the level in it, so use that
    logLevels = ['[DEBUG]','[INFO]','[WARNING]','[ERROR]','[FAULT]']
    logLine = False
    for level in logLevels:
        if level in ln:
            logLine = True
            break
    if not logLine:
        # we don't know how to get the datetime
        return None
    # we SHOULD be able to get th Datetime
    # ex: 2022-12-14 13:51:40,189 [utils] [INFO] dspsr cmd:
    ts = ln.split(',')[0][-19:]
    frmt = "%Y-%m-%d %H:%M:%S"
    dt = datetime.strptime(ts, frmt)
    utc = timezone.utc
    return dt.replace(tzinfo=utc)

def parseCycspecLogFile(fn, start, end=None):
    "Return those lines in the given file betwen given time range"
    with open(fn, 'r') as f:
        lines = f.readlines()
    ls = []
    startIdx = endIdx = None
    firstDt = True
    # if end is not specified, we want to go to last line
    if end is None:
        endIdx = len(lines)
    for i, l in enumerate(lines):
        dt = getDtFromLogLine(l)
        #if dt is None and startIdx is None:
            # if we haven't started, don't include
        #    continue
        if dt is None:
            # no info with which to make a decision
            continue
        if dt < start:
            firstDt = False
            continue
        if dt >= start and startIdx is None:
            # start marking off what we want
            # do we need to take into account stuff from before?
            if firstDt:
                firstDt = False
                startIdx = 0
            else:
                startIdx = i
        if end is not None and dt > end and endIdx is None:
            endIdx = i
    # if we didn't find the end, then we want it all
    if endIdx is None:
        endIdx = len(lines)
    print("start, end, # lines: ", startIdx, endIdx, len(lines))
    return lines[startIdx:endIdx]

def parseCycspecLogFiles(processName, host, start, end=None, ygorDir=None):
    "For the given host and time range, what are the logs for the given process?"
    print("parsecycspecLogFiles: ", processName, host, start, end, ygorDir)
    logs = getCycspecLogFiles(processName, host, start, end=end, ygorDir=ygorDir)
    print(logs)
    print("num log files: ", len(logs))
    # now get all the lines from these logs
    i = 0
    lines = []
    for dt, fn in logs:
        print("Parsing: ", dt, fn)
        # if our given date range spans the entire log, this is easy
        # DOn't do this!  You can't take into account gaps in the
        # files!
       # if i < len(logs) and start < dt and end > logs[i+1][0]:
       #     # read whole file!
       #     print("reading whole file: ", fn)
       #     with open(fn, 'r') as f:
       #         lines.extend(f.readlines())
       # else:
            # we only want part of the file
        lines.extend(parseCycspecLogFile(fn, start, end))
    return lines

def getCycspecLogFiles(processName, host, start, end=None, ygorDir=None):
    "For the given host and time range, what are the log files for the given process?"

    if end is not None and end > start:
        logging.error("end > start so setting end to None")
        end = None

    if ygorDir is None:
        ygorDir = settings.YGOR_TELESCOPE
    logDir = os.path.join(ygorDir, 'etc/log', host)
    processPath = os.path.join(logDir, processName)
    logs = list(filter(os.path.isfile, glob.glob(processPath + "*")))
    # we'd like to sort by creation or modification time, but
    # I'd rather sort by the name in the file
    logs = sorted([(getDtFromLogName(f), f) for f in logs])
    logDts = [dt for dt, f in logs]

    # watch out for the simple case where they are asking
    # for the last log file
    if start > logDts[-1]:
        return [logs[-1]]

    # so, what logs span our given time?
    startIdx = endIdx = None
    for i, logDt in enumerate(logDts):
        if logDt > start and startIdx is None:
            # this is the first log that starts after we
            # want logs from, so there are entries we want
            # from the previous log
            startIdx = i - 1
            print("setting startIdx: ", startIdx, logDt, start)
        if logDt > end and endIdx is None and end is not None:
            # if we're looking for where to end, and
            # this log starts after we want logs to end from,
            # then we should have stopped with the previous
            # log file
            endIdx = i - 1
            print("setting endIdx: ", endIdx, logDt, end)
    # if we didn't specify an end, then we stop with the
    # last log file
    if end is None and endIdx is None:
        endIdx = len(logDts)
    # watch out for cases where we start before the first log
    if startIdx == -1:
        startIdx = 0
    if endIdx == -1 or endIdx == 0:
        endIdx = 1
    # recall that x[y:y] is an empty list
    if startIdx == endIdx:
        endIdx += 1

    # So here are the log files that contain our logs of intersest!
    print(startIdx, endIdx)
    return logs[startIdx:endIdx]
