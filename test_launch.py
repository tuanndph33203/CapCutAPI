import sys, os, time, subprocess
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, 'src')
import win32gui, win32process, psutil

def capcut_pids():
    pids = set()
    for p in psutil.process_iter(['pid', 'name']):
        name = (p.info.get('name') or '').lower()
        if 'capcut' in name or 'jianying' in name:
            pids.add(p.info['pid'])
    return pids

def list_qt_visible(pids):
    results = []
    def enum(hwnd, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                vis = win32gui.IsWindowVisible(hwnd)
                cls = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                area = max(0, rect[2]-rect[0]) * max(0, rect[3]-rect[1])
                if 'Qt' in cls and vis and area > 100000:
                    results.append((hwnd, cls, title[:40], rect, area))
        except: pass
    try: win32gui.EnumWindows(enum, None)
    except: pass
    return results

# Kill
print('Killing CapCut...')
os.system('taskkill /im CapCut.exe /f >nul 2>&1')
time.sleep(1.5)

userprofile = os.environ.get('USERPROFILE', r'C:\Users\admin.TRANANH')
shortcut = os.path.join(userprofile, 'Desktop', 'CapCut.lnk')
if not os.path.exists(shortcut):
    shortcut = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'CapCut', 'CapCut.lnk')

print(f'Launching via os.startfile: {shortcut}', flush=True)
try:
    os.startfile(shortcut)
except Exception as e:
    print(f'os.startfile failed ({e}), falling back to direct exe launch...', flush=True)
    exe = r'C:\Users\admin.TRANANH\AppData\Local\CapCut\Apps\CapCut.exe'
    subprocess.Popen([exe, '--src1'])

for i in range(120):
    time.sleep(1.0)
    pids = capcut_pids()
    qt = list_qt_visible(pids)
    if qt:
        h, c, t, rect, a = qt[0]
        print(f"t={i+1}s: PIDs={len(pids)} main_hwnd={h} rect={rect} is_visible={win32gui.IsWindowVisible(h)}", flush=True)
    else:
        print(f"t={i+1}s: PIDs={len(pids)} (no Qt window detected)", flush=True)
else:
    print('TIMEOUT')
    pids = capcut_pids()
    print(f'Final PIDs={pids}')
