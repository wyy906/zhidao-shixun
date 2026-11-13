"""Windows NTFS real-machine gate check for V2-04A plan A-prime (V2-04B stage A).

Executes the V2-04A verification matrix items that do not require Docker:
NtCreateFile open parameters, RootDirectory relative opens, OBJ_DONT_REPARSE
behavior (normal dir / intermediate junction / final reparse point), DOS drive
mapping, STATUS_REPARSE_POINT_ENCOUNTERED return value, FileId/volume serial
identity comparison, delete authorization paths (file DELETE vs parent
FILE_DELETE_CHILD), sharing-mode vs DACL error classification, and handle
cleanup.

Output: per-item PASS / FAIL / BLOCKED / NOT TESTED lines (English, ASCII safe
for GBK consoles) plus a summary. Exit code is always 0 (reporting tool);
judgement is human/agent review, not exit code.

This script runs under the CURRENT user token. It creates junctions and files
ONLY inside a fresh temp directory that it removes at the end.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
from ctypes import wintypes  # noqa: F401

KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
NTDLL = ctypes.WinDLL("ntdll", use_last_error=True)
ADVAPI32 = ctypes.WinDLL("advapi32", use_last_error=True)

# ---- constants (V2-04A approved values) ----
FILE_OPEN = 0x1                      # CreateDisposition
FILE_DIRECTORY_FILE = 0x1            # CreateOptions
FILE_NON_DIRECTORY_FILE = 0x40
OBJ_CASE_INSENSITIVE = 0x40
OBJ_DONT_REPARSE = 0x1000
SHARE_READ = 0x1
SHARE_NONE = 0x0
DA_DIR = 0x00120080                  # SYNCHRONIZE|READ_CONTROL|FILE_READ_ATTRIBUTES
DA_FILE = 0x00120081                 # + FILE_READ_DATA
STATUS_SUCCESS = 0x00000000
STATUS_REPARSE_POINT_ENCOUNTERED = 0xC000050B  # per MS moderator answer
ERROR_SHARING_VIOLATION = 32
ERROR_ACCESS_DENIED = 5
ERROR_FILE_NOT_FOUND = 2

# ---- structures (64-bit, layout assertions included) ----
class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort),
                ("MaximumLength", ctypes.c_ushort),
                ("Buffer", ctypes.c_wchar_p)]


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulong),
                ("RootDirectory", ctypes.c_void_p),
                ("ObjectName", ctypes.POINTER(UNICODE_STRING)),
                ("Attributes", ctypes.c_ulong),
                ("SecurityDescriptor", ctypes.c_void_p),
                ("SecurityQualityOfService", ctypes.c_void_p)]


class IO_STATUS_BLOCK(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("Status", ctypes.c_long), ("Pointer", ctypes.c_void_p)]
    _anonymous_ = ("u",)
    _fields_ = [("u", _U), ("Information", ctypes.c_size_t)]


class FILE_ID_INFO(ctypes.Structure):
    # SDK layout (winbase.h): ULONGLONG VolumeSerialNumber; FILE_ID_128 FileId;
    # -> VolumeSerialNumber at offset 0 (64-bit!), FileId at offset 8, size 24.
    # VolumeSerialNumber is 64-bit, NOT a 32-bit DWORD. A smaller buffer makes
    # GetFileInformationByHandleEx write past it.
    _fields_ = [("VolumeSerialNumber", ctypes.c_ulonglong),
                ("FileId", ctypes.c_ubyte * 16)]


assert ctypes.sizeof(FILE_ID_INFO) == 24
assert FILE_ID_INFO.VolumeSerialNumber.offset == 0
assert FILE_ID_INFO.FileId.offset == 8


NtCreateFile = NTDLL.NtCreateFile
NtCreateFile.restype = ctypes.c_long
NtCreateFile.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong,
                         ctypes.POINTER(OBJECT_ATTRIBUTES),
                         ctypes.POINTER(IO_STATUS_BLOCK),
                         ctypes.POINTER(ctypes.c_longlong), ctypes.c_ulong,
                         ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                         ctypes.c_void_p, ctypes.c_ulong]

KERNEL32.LocalFree.restype = ctypes.c_void_p
KERNEL32.LocalFree.argtypes = [ctypes.c_void_p]
KERNEL32.CreateFileW.restype = ctypes.c_void_p
KERNEL32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                 ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                 ctypes.c_void_p]
KERNEL32.DeleteFileW.restype = ctypes.c_int
KERNEL32.DeleteFileW.argtypes = [ctypes.c_wchar_p]
KERNEL32.GetFileInformationByHandleEx.restype = ctypes.c_int
KERNEL32.GetFileInformationByHandleEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                  ctypes.c_void_p, ctypes.c_ulong]
KERNEL32.GetVolumeInformationW.restype = ctypes.c_int
KERNEL32.GetVolumeInformationW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                           ctypes.c_ulong, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_wchar_p, ctypes.c_ulong]
ADVAPI32.GetSecurityInfo.restype = ctypes.c_long
ADVAPI32.GetSecurityInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                     ctypes.POINTER(ctypes.c_void_p),   # ppsidOwner
                                     ctypes.POINTER(ctypes.c_void_p),   # ppsidGroup
                                     ctypes.POINTER(ctypes.c_void_p),   # ppDacl
                                     ctypes.POINTER(ctypes.c_void_p),   # ppSacl
                                     ctypes.POINTER(ctypes.c_void_p)]   # ppSecurityDescriptor
ADVAPI32.GetNamedSecurityInfoW.restype = ctypes.c_long
ADVAPI32.GetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong,
                                           ctypes.c_ulong,
                                           ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p)]
ADVAPI32.GetAce.restype = ctypes.c_int
ADVAPI32.GetAce.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                            ctypes.POINTER(ctypes.c_void_p)]


def acl_ace_info(pacl):
    """Return (ace_count, [(ace_type, mask), ...]) for an ACL pointer (int)."""
    if not pacl:
        return 0, []
    count = ctypes.c_ushort.from_address(pacl + 4).value
    out = []
    ptr = ctypes.c_void_p()
    for i in range(count):
        if ADVAPI32.GetAce(ctypes.c_void_p(pacl), i, ctypes.byref(ptr)) and ptr.value:
            ace_type = ctypes.c_ubyte.from_address(ptr.value).value
            mask = ctypes.c_ulong.from_address(ptr.value + 4).value
            out.append((ace_type, mask))
    return count, out

RESULTS = []


def record(item, desc, status, detail):
    RESULTS.append((item, desc, status, detail))
    print("[%-10s] %-8s %s | %s" % (status, item, desc, detail))


def nt_open(nt_path=None, root=None, desired=DA_DIR, share=SHARE_READ,
            create_opts=FILE_DIRECTORY_FILE, attrs=OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE):
    """Open via NtCreateFile. Returns (status, handle, io_status)."""
    oa = OBJECT_ATTRIBUTES()
    oa.Length = ctypes.sizeof(OBJECT_ATTRIBUTES)
    us = None
    if nt_path is not None:
        us = UNICODE_STRING(len(nt_path) * 2, (len(nt_path) + 1) * 2, None)
        us.Buffer = nt_path  # ctypes keeps the converted buffer alive on the struct
        oa.ObjectName = ctypes.pointer(us)
    oa.RootDirectory = root
    oa.Attributes = attrs
    ios = IO_STATUS_BLOCK()
    handle = ctypes.c_void_p()
    # NtCreateFile parameter order: ..., FileAttributes, ShareAccess,
    # CreateDisposition, CreateOptions, ... (disposition BEFORE options)
    st = NtCreateFile(ctypes.byref(handle), desired, ctypes.byref(oa),
                      ctypes.byref(ios), None, 0, share, FILE_OPEN,
                      create_opts, None, 0)
    return st, handle, ios


def nt_close(handle):
    if handle and handle.value:
        KERNEL32.CloseHandle(handle)
        handle.value = None


def file_id_of(handle):
    info = FILE_ID_INFO()
    ok = KERNEL32.GetFileInformationByHandleEx(handle, 18, ctypes.byref(info),
                                              ctypes.sizeof(info))
    if not ok:
        return None, KERNEL32.GetLastError()
    return (info.VolumeSerialNumber, bytes(info.FileId)), 0


def main():
    import platform
    print("=== Windows NTFS gate check (V2-04B stage A) ===")
    print("python:", sys.version.split()[0], "| build:", platform.version())

    # ---- T000 struct layout assertions (ctypes ABI gate) ----
    sizes = (ctypes.sizeof(UNICODE_STRING), ctypes.sizeof(OBJECT_ATTRIBUTES),
             ctypes.sizeof(IO_STATUS_BLOCK), ctypes.sizeof(FILE_ID_INFO))
    offsets_ok = (FILE_ID_INFO.VolumeSerialNumber.offset == 0
                  and FILE_ID_INFO.FileId.offset == 8)
    record("T000", "struct sizes US/OBJA/IOSB/FILE_ID_INFO (expect 16/48/16/24 on x64; VSN@0 FileId@8)",
           "PASS" if sizes == (16, 48, 16, 24) and offsets_ok else "FAIL",
           str(sizes) + " offsets_ok=%s" % offsets_ok)
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        record("T000b", "pointer size", "BLOCKED", "not a 64-bit process")
        return

    # ---- volume FS type: PASS only when actually NTFS ----
    fsbuf = ctypes.create_unicode_buffer(261)
    ok = KERNEL32.GetVolumeInformationW("C:\\", None, 0, None, None, None,
                                        fsbuf, 261)
    if not ok:
        record("T001", "C: volume filesystem", "BLOCKED",
               "GetVolumeInformationW failed err=%d" % KERNEL32.GetLastError())
    else:
        fs = fsbuf.value
        record("T001", "C: volume filesystem", "PASS" if fs.upper() == "NTFS" else "FAIL",
               "%s (expect NTFS)" % fs)

    # ---- token type (evidence for token classification) ----
    try:
        out = subprocess.run(["whoami", "/groups"], capture_output=True,
                             text=True).stdout
        elevated = ("S-1-16-12288" in out)
        deny_only = ("Group used for deny only" in out)
        record("T002", "current token type",
               "PASS", "elevated=%s administrators_deny_only=%s (UAC filtered=%s)"
               % (elevated, deny_only, not elevated and deny_only))
    except Exception as exc:  # noqa: BLE001
        record("T002", "current token type", "BLOCKED", repr(exc))

    base = os.path.join(tempfile.gettempdir(), "zd_gate_%d" % os.getpid())
    nt_base = "\\??\\" + base  # \??\C:\...  (4-char NT prefix)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    real_target = os.path.join(base, "real_target")
    os.makedirs(real_target)
    with open(os.path.join(real_target, "marker.txt"), "w") as f:
        f.write("gate")
    junction = os.path.join(base, "junc")
    mk = subprocess.run(["cmd", "/c", "mklink", "/J", junction, real_target],
                        capture_output=True, text=True)
    junc_ok = ("Junction created" in mk.stdout) or ("created" in mk.stdout.lower())
    record("T003", "create test junction for reparse tests",
           "PASS" if junc_ok else "BLOCKED",
           mk.stdout.strip() or mk.stderr.strip())

    handles = []
    try:
        # ---- T010 trusted base dir open (plan A-prime full parameter set) ----
        st, h, ios = nt_open(nt_path=nt_base, attrs=OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE)
        handles.append(h)
        record("T010", "NtCreateFile dir open: FILE_DIRECTORY_FILE+OBJ_DONT_REPARSE, absolute \\??\\ path",
               "PASS" if st == STATUS_SUCCESS else "FAIL",
               "status=0x%08X ios=0x%08X" % (st & 0xFFFFFFFF, ios.Status & 0xFFFFFFFF))
        dir_h = h

        # ---- T011 same, without OBJ_DONT_REPARSE (control) ----
        st2, h2, _ = nt_open(nt_path=nt_base, attrs=OBJ_CASE_INSENSITIVE)
        handles.append(h2)
        record("T011", "control: dir open without OBJ_DONT_REPARSE",
               "PASS" if st2 == STATUS_SUCCESS else "FAIL",
               "status=0x%08X" % (st2 & 0xFFFFFFFF))
        nt_close(h2)

        # ---- T020 file open relative to dir handle (plan A-prime file params) ----
        with open(os.path.join(base, "gate.txt"), "w") as f:
            f.write("hello")
        st, fh, _ = nt_open(nt_path="gate.txt", root=dir_h.value if dir_h.value else None,
                            desired=DA_FILE, create_opts=FILE_NON_DIRECTORY_FILE)
        handles.append(fh)
        record("T020", "NtCreateFile file open relative to RootDirectory: FILE_NON_DIRECTORY_FILE",
               "PASS" if st == STATUS_SUCCESS else "FAIL",
               "status=0x%08X" % (st & 0xFFFFFFFF))

        # ---- T021 subdir relative open ----
        os.makedirs(os.path.join(base, "sub"))
        st, sh, _ = nt_open(nt_path="sub", root=dir_h.value, create_opts=FILE_DIRECTORY_FILE)
        handles.append(sh)
        record("T021", "NtCreateFile subdir open relative to RootDirectory",
               "PASS" if st == STATUS_SUCCESS else "FAIL",
               "status=0x%08X" % (st & 0xFFFFFFFF))

        # ---- T030 FileId identity: same object via two open paths ----
        if fh and fh.value:
            id_rel, err1 = file_id_of(fh)
            st3, h3, _ = nt_open(nt_path=nt_base + "\\gate.txt", desired=DA_FILE,
                                 create_opts=FILE_NON_DIRECTORY_FILE)
            handles.append(h3)
            id_abs, err2 = file_id_of(h3)
            same = (id_rel is not None and id_rel == id_abs)
            record("T030", "FileId+VolumeSerial identity: relative vs absolute open of same file",
                   "PASS" if same else "FAIL",
                   "rel=%s(abs%d) abs=%s(abs%d) same=%s" % (
                       ("0x%X/%s" % (id_rel[0], id_rel[1].hex())) if id_rel else None, err1,
                       ("0x%X/%s" % (id_abs[0], id_abs[1].hex())) if id_abs else None, err2, same))

        # ---- T040 OBJ_DONT_REPARSE: final component = junction ----
        if junc_ok:
            st, jh, _ = nt_open(nt_path=nt_base + "\\junc", create_opts=FILE_DIRECTORY_FILE)
            handles.append(jh)
            blocked = ((st & 0xFFFFFFFF) == STATUS_REPARSE_POINT_ENCOUNTERED)
            record("T040", "OBJ_DONT_REPARSE: final component junction -> expect fail 0xC000050B",
                   "PASS" if blocked else "FAIL",
                   "status=0x%08X expected=0xC000050B" % (st & 0xFFFFFFFF))

            # ---- T041 intermediate junction ----
            st, ih, _ = nt_open(nt_path="junc\\marker.txt", root=dir_h.value,
                                desired=DA_FILE, create_opts=FILE_NON_DIRECTORY_FILE)
            handles.append(ih)
            blocked = ((st & 0xFFFFFFFF) == STATUS_REPARSE_POINT_ENCOUNTERED)
            record("T041", "OBJ_DONT_REPARSE: intermediate junction via RootDirectory -> expect fail",
                   "PASS" if blocked else "FAIL",
                   "status=0x%08X expected=0xC000050B" % (st & 0xFFFFFFFF))

            # ---- T042 control: follow junction without the flag ----
            st, jh2, _ = nt_open(nt_path=nt_base + "\\junc", create_opts=FILE_DIRECTORY_FILE,
                                 attrs=OBJ_CASE_INSENSITIVE)
            handles.append(jh2)
            followed = (st == STATUS_SUCCESS)
            # identity: followed handle should match real_target's own FileId
            st4, th, _ = nt_open(nt_path=nt_base + "\\real_target",
                                 create_opts=FILE_DIRECTORY_FILE, attrs=OBJ_CASE_INSENSITIVE)
            handles.append(th)
            same_target = followed and file_id_of(jh2) == file_id_of(th)
            record("T042", "control: without flag junction is followed (opened), target identity matches",
                   "PASS" if (followed and same_target) else "FAIL",
                   "followed=%s same_target=%s status=0x%08X" % (followed, same_target, st & 0xFFFFFFFF))
        else:
            record("T040", "OBJ_DONT_REPARSE junction tests", "BLOCKED",
                   "junction creation failed")
            record("T041", "OBJ_DONT_REPARSE junction tests", "BLOCKED", "see T003")
            record("T042", "junction follow control", "BLOCKED", "see T003")

        # ---- T050 drive-letter mapping under OBJ_DONT_REPARSE ----
        # T010 already proved \??\C:\ absolute open succeeds with the flag set;
        # additionally verify a nested path through C: works:
        st, dh, _ = nt_open(nt_path=nt_base + "\\sub", create_opts=FILE_DIRECTORY_FILE)
        handles.append(dh)
        record("T050", "DOS drive-letter mapping (\\??\\C:) resolves under OBJ_DONT_REPARSE",
               "PASS" if st == STATUS_SUCCESS else "FAIL",
               "status=0x%08X" % (st & 0xFFFFFFFF))

        # ---- T060 security descriptor query on dir handle ----
        # Receive ppSecurityDescriptor and free only the descriptor itself
        # (Owner/DACL pointers point inside it). Free in finally so exception
        # paths cannot leak.
        owner_sid = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        sd = ctypes.c_void_p()
        try:
            rv = ADVAPI32.GetSecurityInfo(dir_h.value, 1, 0x1 | 0x4,
                                          ctypes.byref(owner_sid), None,
                                          ctypes.byref(dacl), None,
                                          ctypes.byref(sd))
            if rv == 0 and sd.value and dacl.value:
                ace_count, _ = acl_ace_info(dacl.value)
                record("T060", "GetSecurityInfo Owner+DACL by handle (READ_CONTROL path)",
                       "PASS", "sd=0x%X ace_count=%d (current user dir; template compare is deployment-level)"
                       % (sd.value, ace_count))
            else:
                record("T060", "GetSecurityInfo Owner+DACL by handle", "FAIL",
                       "rv=0x%08X err=%d sd=%s" % (rv, KERNEL32.GetLastError(), bool(sd.value)))
        finally:
            if sd.value:
                KERNEL32.LocalFree(ctypes.c_void_p(sd.value))

        # ---- T070 delete positive path (file DELETE authorized) ----
        del_path = os.path.join(base, "del_pos.txt")
        open(del_path, "w").close()
        ok = KERNEL32.DeleteFileW(del_path)
        record("T070", "positive: file DELETE authorized -> DeleteFileW succeeds",
               "PASS" if ok else "FAIL",
               "err=%d" % (0 if ok else KERNEL32.GetLastError()))

        # ---- T071 sharing violation vs DACL denial classification ----
        shr_path = os.path.join(base, "shr.txt")
        open(shr_path, "w").close()
        gh = KERNEL32.CreateFileW(shr_path, 0x80000000, SHARE_READ, None,
                                  3, 0x80, None)  # GENERIC_READ, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL
        if gh and gh not in (0, 0xFFFFFFFFFFFFFFFF):
            gh_h = ctypes.c_void_p(gh)
            handles.append(gh_h)
            KERNEL32.DeleteFileW(shr_path)
            err = KERNEL32.GetLastError()
            record("T071", "held handle w/o FILE_SHARE_DELETE -> DeleteFileW expect ERROR_SHARING_VIOLATION(32)",
                   "PASS" if err == ERROR_SHARING_VIOLATION else "FAIL",
                   "err=%d" % err)
        else:
            record("T071", "sharing-mode test", "BLOCKED",
                   "CreateFileW failed err=%d" % KERNEL32.GetLastError())

        den_path = os.path.join(base, "deny.txt")
        open(den_path, "w").close()
        r = subprocess.run(["icacls", den_path, "/deny", "Everyone:(DE)"],
                           capture_output=True, text=True)
        ok = KERNEL32.DeleteFileW(den_path)
        err = KERNEL32.GetLastError()
        if r.returncode != 0:
            record("T072", "DACL deny DELETE test", "BLOCKED",
                   "icacls failed: " + (r.stderr.strip() or r.stdout.strip()))
        else:
            # Real Windows semantics (V2-04A threat model R-4B-11): deletion is
            # authorized by file DELETE *or* parent FILE_DELETE_CHILD. A deny on
            # the file alone must NOT prevent deletion when the parent grants
            # the delete-child path. Expect: deletion SUCCEEDS via parent path.
            record("T072", "file DACL deny DELETE but parent has delete path -> deletion succeeds (proves parent-authorization path)",
                   "PASS" if ok else "FAIL",
                   "deleted=%s err=%d (deny on file alone does not stop deletion)" % (ok, err))
        subprocess.run(["icacls", den_path, "/reset"], capture_output=True, text=True)
        KERNEL32.DeleteFileW(den_path)

        # ---- T073 parent FILE_DELETE_CHILD authorized path ----
        # FILE_DELETE_CHILD (0x40) is NOT grantable via icacls letters; use the
        # .NET FileSystemAccessRule 'DeleteSubdirectoriesAndFiles' (= 0x40).
        dcd = os.path.join(base, "dchild")
        os.makedirs(dcd)
        ps_script = (
            "$d = '%s';\n"
            "$acl = Get-Acl $d\n"
            "$acl.SetAccessRuleProtection($true, $false)\n"
            "$r1 = New-Object System.Security.AccessControl.FileSystemAccessRule("
            "'Everyone','WriteData','None','None','Allow')\n"
            "$r2 = New-Object System.Security.AccessControl.FileSystemAccessRule("
            "'Everyone','DeleteSubdirectoriesAndFiles','None','None','Allow')\n"
            "$acl.AddAccessRule($r1); $acl.AddAccessRule($r2)\n"
            "Set-Acl $d $acl\n"
        ) % dcd.replace("'", "''")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script],
                           capture_output=True, text=True)
        grant_ok = (r.returncode == 0)
        if grant_ok:
            fpath = os.path.join(dcd, "victim.txt")
            open(fpath, "w").close()  # parent grants WD (add file); file gets empty DACL

            # Evidence A: child DACL is present, non-NULL, and has zero ACEs.
            child_dacl = ctypes.c_void_p()
            child_sd = ctypes.c_void_p()
            # Evidence B: parent DACL really contains a FILE_DELETE_CHILD(0x40) grant.
            parent_dacl = ctypes.c_void_p()
            parent_sd = ctypes.c_void_p()
            ev_a = ev_b = False
            details = []
            try:
                rv1 = ADVAPI32.GetNamedSecurityInfoW(fpath, 1, 0x4, None, None,
                                                     ctypes.byref(child_dacl), None,
                                                     ctypes.byref(child_sd))
                if rv1 == 0 and child_dacl.value:
                    n_child, aces_child = acl_ace_info(child_dacl.value)
                    ev_a = (n_child == 0)
                    details.append("child_dacl_present=True ace_count=%d" % n_child)
                else:
                    details.append("child_dacl NULL (rv=0x%08X) -> null-DACL semantics unproven" % rv1)

                rv2 = ADVAPI32.GetNamedSecurityInfoW(dcd, 1, 0x4, None, None,
                                                     ctypes.byref(parent_dacl), None,
                                                     ctypes.byref(parent_sd))
                if rv2 == 0 and parent_dacl.value:
                    n_par, aces_par = acl_ace_info(parent_dacl.value)
                    dc_granted = any(t == 0 and (m & 0x40) for t, m in aces_par)
                    ev_b = dc_granted
                    details.append("parent_ace_count=%d FILE_DELETE_CHILD_granted=%s aces=%s"
                                   % (n_par, dc_granted, aces_par))
                else:
                    details.append("parent_dacl NULL (rv=0x%08X)" % rv2)

                # Evidence C: deletion succeeds via the parent path.
                ok = KERNEL32.DeleteFileW(fpath)
                err = 0 if ok else KERNEL32.GetLastError()
                record("T073", "parent FILE_DELETE_CHILD-only grant -> empty-DACL child deleted via parent path",
                       "PASS" if (ev_a and ev_b and ok) else "FAIL",
                       "deleted=%s err=%d ev_child_empty=%s ev_parent_dc=%s | %s"
                       % (ok, err, ev_a, ev_b, "; ".join(details)))
            finally:
                if child_sd.value:
                    KERNEL32.LocalFree(ctypes.c_void_p(child_sd.value))
                if parent_sd.value:
                    KERNEL32.LocalFree(ctypes.c_void_p(parent_sd.value))
        else:
            record("T073", "parent FILE_DELETE_CHILD test", "BLOCKED",
                   "Set-Acl failed: " + (r.stderr.strip() or r.stdout.strip())[:200])

        # ---- T080 cleanup / handle release ----
        for h in handles:
            nt_close(h)
        try:
            os.rmdir(junction)
        except OSError:
            pass
        shutil.rmtree(base, ignore_errors=True)
        gone = not os.path.exists(base)
        record("T080", "all handles closed, temp dir removed", "PASS" if gone else "FAIL",
               "base removed=%s" % gone)
    finally:
        for h in handles:
            nt_close(h)
        try:
            os.rmdir(junction)
        except OSError:
            pass
        shutil.rmtree(base, ignore_errors=True)

    print("=== summary ===")
    counts = {}
    for _, _, st, _ in RESULTS:
        counts[st] = counts.get(st, 0) + 1
    for k in ("PASS", "FAIL", "BLOCKED", "NOT TESTED"):
        print("%-10s %d" % (k, counts.get(k, 0)))


if __name__ == "__main__":
    main()
