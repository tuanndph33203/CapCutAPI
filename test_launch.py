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

shortcut = r'C:\Users\PC\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\CapCut\CapCut.lnk'
print(f'Launching via explorer.exe: {shortcut}')
subprocess.Popen(['explorer.exe', shortcut])

for i in range(80):
    time.sleep(0.5)
    elapsed = (i+1)*0.5
    pids = capcut_pids()
    qt = list_qt_visible(pids)
    if qt:
        print(f't={elapsed:.1f}s SUCCESS! CapCut window visible:')
        for w in qt:
            print(f'  hwnd={w[0]} cls={w[1]!r} title={w[2]!r} area={w[4]}')
        break
    if i % 6 == 0:
        print(f't={elapsed:.1f}s PIDs={len(pids)}')
else:
    print('TIMEOUT')
    pids = capcut_pids()
    print(f'Final PIDs={pids}')
