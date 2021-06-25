import os
import xbmc
import xbmcgui
import xbmcvfs
import sys
import json
import base64
import zlib
import requests
import time
import datetime

from lib import config, logger, install

IsPY3 = True if sys.version_info[0] >= 3 else False

if IsPY3:
    from xbmcvfs import translatePath
else:
    from xbmc import translatePath

ADDON_NAME = "World Live TV"
API_DOMAIN = 'http://tvchannels.worldlivetv.eu/tv'
EPG_URL = 'http://epg-guide.com/wltv.gz'
FILE_REPO = 'http://www.worldlivetv.eu/world/files'
ADDON_REPO_PATCH = 'https://crack75.github.io/repo/plugin.video.wltvhelper.patch'
LAST_CHK_INF = 'lastcheck.inf'
SETTINGS_FILE = 'settings.xml'
PATCH_FILE = 'patch.zip'
PATCH_FILE_INFO = 'patch.json'

DEFAULT_DATE = 20210101

RemoteLists = []

PARAM_LIST_NAME = 'personal_list'

def PY3():
    return IsPY3

def apiRequester(par = ''):
    return requests.get(API_DOMAIN + par).json()

def readFile(filePath):
    file = xbmcvfs.File(filePath)
    c = file.read()
    file.close()

    return c

def writeFile(filePath, input):
    file = xbmcvfs.File(filePath, 'w')
    file.write(input)
    file.close()

def downloadFile(url, filePath, returnContent = False): #duplice funzione
    req = requests.get(url, allow_redirects=True)
    if(filePath != ''):
        writeFile(filePath, req.content)
        #open(filePath, 'wb').write(req.content) #py2 gets [Errno 22] invalid mode ('wb') write in binary mode
    if returnContent:
        return req.content

def extract(zipFilePath, destination): # alternative to xbmc.executebuiltin(Extract
    import zipfile # non serve altrove

    with zipfile.ZipFile(zipFilePath,"r") as zip:
        zip.extractall(destination)

def getPersonalPathFile(filename):
    file_path = os.path.join(config.ADDONUSERPATH, filename)

    return translatePath(file_path)

def readLocalOrDownload(fileName, checkServerFileTimeStamp = True, onceaday = True):
    fileContent = ''
    filePath = os.path.join(config.ADDONUSERPATH, fileName)

    forceDownload = needsUpdate(fileName, FILE_REPO, checkServerFileTimeStamp, onceaday)

    if(not forceDownload):
        try:
            fileContent = readFile(filePath)
        except:
            fileContent = ''

    if (not fileContent or forceDownload):
        url = '{}/{}'.format(FILE_REPO, fileName)
        fileContent = downloadFile(url, filePath, True)

    return fileContent

def needsUpdate(filename, remotePath, checkServerFileTimeStamp = False, onceaday = True):
    res = False
    filePath = translatePath(os.path.join(config.ADDONUSERPATH, filename))

    logger.info('Check update for File: {}, FromServer: {}, Once a Day: {}'.format(filename, checkServerFileTimeStamp, onceaday))
    if not os.path.exists(filePath):
        logger.info('Cannot get localfile {}, needs update'.format(filename))
        res = True
    else:
        try:
            if (checkServerFileTimeStamp):
                last_modified_date = datetime.datetime.fromtimestamp(os.path.getmtime(filePath))
                day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][last_modified_date.weekday()]
                
                if(onceaday):
                    modified_since = last_modified_date.strftime("%d %b %Y 23:59:59 GTM") #once a day it's enought
                else:
                    modified_since = last_modified_date.strftime("%d %b %Y %H:%M:%S GTM")

                url = '{}/{}'.format(remotePath, filename)
                req = requests.get(url, headers={'If-Modified-Since': '{}, {}'.format(day, modified_since) })
                status = req.status_code

                if status == 404: #not found on server
                    res = False
                elif req.status_code != 304: # cannot read from local file because of CACHE, needs update
                    res = True
                logger.info('Query status code: {} is changed: {}'.format(req.status_code, res))
            else:
                dt = datetime.datetime.now()
                file_datetime = datetime.datetime.fromtimestamp(os.path.getctime(filePath))
                res = (dt - file_datetime).days > 1
        except OSError as e:
            logger.info('Error getting localfile info {}, needs update'.format(filename), e)
            res = True
        except Exception as e:
            logger.info('Error during needsUpdate check: [{}]'.format(e))
            logger.info('Force download {}'.format(filename))
            res = True

    return res

def checkForUpdates(forced = False):
    res = False
    autoupdate = config.getSetting('autoupdate')

    if autoupdate or forced:
        itsTimeToCheck = False
        fileTimer = translatePath(os.path.join(config.ADDONUSERPATH, LAST_CHK_INF))

        if os.path.exists(fileTimer):
            t = time.time() - os.path.getmtime(fileTimer)
            if t > 3600: # check ogni ora
                itsTimeToCheck = True
        else:
            itsTimeToCheck = True

        if itsTimeToCheck:
            try:
                res = installUpdates()
            except:
                pass

            writeFile(fileTimer, str(datetime.datetime.fromtimestamp(time.time())))

    return res

def installUpdates():
    res = False
    verServerString = ''
    verServerNumber = 0
    patchServerNumber = 0
    patchFileServer = ''
    verLocalNumber = 0
    patchLocalNumber = 0
    updateDescription = ''

    url = '{}/{}'.format(ADDON_REPO_PATCH, PATCH_FILE_INFO)
    localPatchInfoFile = translatePath(os.path.join(config.ADDONUSERPATH, PATCH_FILE_INFO))

    try:
        patchServerJson = requests.get(url).json()
        
        for patchServer in patchServerJson:
            verServerString = patchServer['version']
            verDestination = patchServer['destination']
            if(verDestination == config.ADDONVERSION):
                verServerNumber = int(verServerString.replace('.',''))
                patchFileServer = patchServer['filename']
                typeofupdate = patchServer['type']
                patchServerNumber = patchServer['patch']
                updateDescription = patchServer['description']
                break

        if os.path.isfile(localPatchInfoFile):
            patchLocalJson = json.loads(readFile(localPatchInfoFile))
            verLocalNumber = int(patchLocalJson['version'].replace('.',''))
            patchLocalNumber = patchLocalJson['patch']
    except :
        pass #local json do not exists, I keep default values

    updateAvailable = (verServerNumber > verLocalNumber) or (verServerNumber == verLocalNumber and patchServerNumber > patchLocalNumber)

    if updateAvailable:
        dataFile = translatePath(os.path.join(config.ADDONUSERPATH, PATCH_FILE))
        logger.info('A new {} update (v.{}.{}) is available... download and install...'.format(typeofupdate, verServerString, patchServerNumber))
        if os.path.isfile(dataFile):
            os.remove(dataFile)

        url = '{}/{}'.format(ADDON_REPO_PATCH, patchFileServer)
        downloadFile(url, dataFile)

        #extract(dataFile, config.ROOTADDONPATH)
        xbmc.executebuiltin('Extract({}, {})'.format(dataFile, config.ROOTADDONPATH)) 
        xbmc.executebuiltin("UpdateLocalAddons")
        #xbmc.executebuiltin("UpdateAddonRepos")
        xbmc.sleep(1500)

        writeFile(localPatchInfoFile, str(json.dumps(patchServer)))
        writeFile(dataFile, 'update applied')
        logger.info('New {} update (v.{}.{}) installed'.format(typeofupdate, verServerString, patchServerNumber))
        strmsg = config.ADDON.getLocalizedString(30133)
        strmsg = strmsg.format(typeofupdate, verServerString, patchServerNumber)
        strmsg = '{}\n\n{}'.format(strmsg, updateDescription)
        xbmcgui.Dialog().ok(ADDON_NAME, strmsg)
        #xbmc.executebuiltin('Notification({}, {}, {})'.format(ADDON_NAME, strmsg, 4000))
        res = True
    else:
        logger.info('No updates available, exit.')

    return res

def forcecheckupdate():
    logger.info('Force check update')
    dir = translatePath(config.ADDONUSERPATH)
    file = os.path.join(dir, LAST_CHK_INF)
    if os.path.isfile(file):
        os.remove(file)
    res = checkForUpdates(True)
    if not res:
        xbmc.executebuiltin('Notification({}, {}, {})'.format(ADDON_NAME, "No patch available", 4000))

def cachecleanup():
    logger.info('Start cache file cleanup')
    dir = translatePath(config.ADDONUSERPATH)

    for filename in os.listdir(dir):
        if filename.endswith('.bin') or filename.endswith('.dat'):
            file = os.path.join(dir, filename)
            if os.path.isfile(file):
                os.remove(file)

    logger.info('File cleanup completed')
    xbmc.executebuiltin('Notification({}, {}, {})'.format(ADDON_NAME, "Cache files has been cleanup!", 4000))

#def DecodeFromBase64(Json):
#    if PY3:
#        return base64.b64encode(json.dumps(Json).encode()).decode()
#    else:
#        return base64.b64encode(json.dumps(Json))
def decodeFromBase64(input):
    return base64.b64decode(input)

###################
def decompress(input):
    decomp = ''
    try:
        decomp = (zlib.decompress(base64.b64decode(input),-15))
    except Exception as e:
        logger.info('Error decompressin files: ', e)

    return decomp

def getRemoteLists():
    res = apiRequester('/all.json')
    for l in res:
        if l['Enabled'] or config.isDEV():
            RemoteLists.append(transformListItem(l))

    return RemoteLists

def transformListItem(item, official = True):
    return {
        'Name': item['Name'],
        'Choose': {},
        'Official': official
    }

def checkSettings():
    import datetime

    useDL = config.getSetting("forceDirectLink")

    dt = int(datetime.datetime.now().date().strftime('%Y%m%d'))
    expDt = int(config.getSetting("forceDirectLinkExp"))

    if(useDL == True and expDt == DEFAULT_DATE):
        config.setSetting("forceDirectLinkExp", dt)
        expDt = dt

    if(abs(dt - expDt) >= 1):
        config.setSetting("forceDirectLink", False)
        config.setSetting("forceDirectLinkExp", DEFAULT_DATE)

    return

def getPersonalLists():
    if not config.getSetting(PARAM_LIST_NAME):
        return []

    listDict = json.loads(config.getSetting(PARAM_LIST_NAME))
    if type(listDict) is str:
        try:
            listDict = json.loads(listDict)
        except:
            # TODO: print error or log?
            listDict = []
    return listDict

def computeListUrl(selectedList):
    selectedGroups = []
    if selectedList['Choose']:
        choosedLists = selectedList['Choose']
        for listKey in choosedLists:
            groups = choosedLists[listKey]
            queryGroups = []
            for group in groups:
                queryGroups.append(group)
            selectedGroups.append('{}={}'.format(listKey, ','.join(queryGroups)))

    if len(selectedGroups) == 0:
        # user has selected a full list
        return '{}/{}/list.m3u8?'.format(API_DOMAIN, selectedList['Name'])
    else:
        return '{}/all/groups/merge.m3u8?{}'.format(API_DOMAIN, '&'.join(selectedGroups))

def setList(listName, m3uList, epgUrl):
    simple = install.install_pvr()

    if simple:
        if PY3():
            xbmc.executebuiltin('xbmc.StopPVRManager')
        else:
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id":1, "method": "Addons.SetAddonEnabled", "params": { "addonid": "pvr.iptvsimple", "enabled": false }}')

        if simple.getSetting('m3uPathType') != '1': simple.setSetting('m3uPathType', '1')
        if simple.getSetting('epgPathType') != '1': simple.setSetting('epgPathType', '1')

        if (epgUrl):
            if simple.getSetting('logoFromEpg') != '2': simple.setSetting('logoFromEpg', '2')
            if simple.getSetting('epgUrl') != epgUrl: simple.setSetting('epgUrl', epgUrl)
            elif simple.getSetting('epgUrl') and not config.getSetting('enable_epg'): simple.setSetting('epgUrl','')
        else:
            simple.setSetting('epgUrl', '')
            simple.setSetting('logoFromEpg', '0')

        simple.setSetting('m3uUrl', m3uList)

        xbmc.sleep(500)

        if PY3():
            xbmc.executebuiltin('xbmc.StartPVRManager')
        else:
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id":1, "method": "Addons.SetAddonEnabled", "params": { "addonid": "pvr.iptvsimple", "enabled": true }}')
            xbmc.sleep(500)
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id":1, "method": "Addons.SetAddonEnabled", "params": { "addonid": "pvr.iptvsimple", "enabled": false }}')
            xbmc.sleep(500)
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id":1, "method": "Addons.SetAddonEnabled", "params": { "addonid": "pvr.iptvsimple", "enabled": true }}')

        # show a simple notification informing user new IPTV list has been set
        if(listName): listName += ' '
        xbmcgui.Dialog().notification(config.getString(30000), config.getString(30120).format(listName))
