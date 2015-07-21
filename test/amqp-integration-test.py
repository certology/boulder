#!/usr/bin/env python2.7
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

tempdir = tempfile.mkdtemp()

class ExitStatus:
    OK, PythonFailure, NodeFailure, Error = range(4)

exit_status = 0

def die(status):
    global exit_status
    exit_status = status
    sys.exit(1)

processes = []


class ProcInfo:
    """
        Args:
            cmd (str): The command that was run
            proc(subprocess.Popen): The Popen of the command run
    """

    def __init__(self, cmd, proc):
        self.cmd = cmd
        self.proc = proc

def run(path, args=""):
    global processes
    binary = os.path.join(tempdir, os.path.basename(path))
    cmd = 'GORACE="halt_on_error=1" go build -tags pkcs11 -race -o %s %s' % (binary, path)
    print(cmd)
    if subprocess.Popen(cmd, shell=True).wait() != 0:
        die(ExitStatus.Error)
    runCmd = "exec %s %s" % (binary, args)
    print(runCmd)
    info = ProcInfo(runCmd, subprocess.Popen(runCmd, shell=True))
    processes.append(info)
    return info

def start():
    run('./cmd/boulder-wfe', '--config test/boulder-test-config.json')
    run('./cmd/boulder-ra', '--config test/boulder-test-config.json')
    run('./cmd/boulder-sa', '--config test/boulder-test-config.json')
    run('./cmd/boulder-ca', '--config test/boulder-test-config.json')
    run('./cmd/boulder-va', '--config test/boulder-test-config.json')
    run('./test/dns-test-srv')

def run_node_test():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('localhost', 4300))
    except socket.error, e:
        print("Cannot connect to WFE")
        die(ExitStatus.Error)

    os.chdir('test/js')

    if subprocess.Popen('npm install', shell=True).wait() != 0:
        print("\n Installing NPM modules failed")
        die(ExitStatus.Error)
    if subprocess.Popen('''
        node test.js --email foo@letsencrypt.org --agree true \
          --domains foo.com --new-reg http://localhost:4300/acme/new-reg \
          --certKey %s/key.pem --cert %s/cert.der
        ''' % (tempdir, tempdir), shell=True).wait() != 0:
        print("\nIssuing failed")
        die(ExitStatus.NodeFailure)
    if subprocess.Popen('''
        node revoke.js %s/cert.der %s/key.pem http://localhost:4300/acme/revoke-cert
        ''' % (tempdir, tempdir), shell=True).wait() != 0:
        print("\nRevoking failed")
        die(ExitStatus.NodeFailure)

    return 0

def run_client_tests():
    root = os.environ.get("LETSENCRYPT_PATH")
    assert root is not None, (
        "Please set LETSENCRYPT_PATH env variable to point at "
        "initialized (virtualenv) client repo root")
    os.environ['SERVER'] = 'http://localhost:4300/acme/new-reg'
    test_script_path = os.path.join(root, 'tests', 'boulder-integration.sh')
    if subprocess.Popen(test_script_path, shell=True, cwd=root).wait() != 0:
        die(ExitStatus.PythonFailure)

try:
    start()
    busted = []
    for pinfo in processes:
        if pinfo.proc.poll() is not None:
            busted.append(pinfo)
    if len(busted) != 0:
        print "\n\nThese processes didn't start up successfully (check above for their output):"
        for pinfo in busted:
            print "\t'%s' exited with %d" % (pinfo.cmd, pinfo.proc.returncode)
        sys.exit(1)

    run_node_test()
    run_client_tests()
except Exception as e:
    exit_status = ExitStatus.Error
    print e
finally:
    for pinfo in processes:
        if pinfo.proc.poll() is None:
            pinfo.proc.kill()
        else:
            exit_status = 1

    shutil.rmtree(tempdir)

    if exit_status == 0:
        print("\n\nSUCCESS")
    else:
        print("\n\nFAILURE")
    sys.exit(exit_status)
