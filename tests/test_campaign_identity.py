"""The external harness must not relabel a different real prompt or benchmark checkout."""
import importlib.util
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest

p=Path(__file__).resolve().parents[1]/'scripts/run_private_campaign.py'
spec=importlib.util.spec_from_file_location('private_campaign',p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class IdentityTests(unittest.TestCase):
    def test_changed_prompt_cannot_use_old_campaign_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths=['src/tessoohey_reader/ai/openai_provider.py','src/tessoohey_reader/ai/models.py','src/tessoohey_reader/semantic/models.py']
            for name in paths:
                (root/name).parent.mkdir(parents=True,exist_ok=True)
                (root/name).write_text('synthetic')
            identity={'scheme':'reader-prompt-files-v1','files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}}
            plan={'prompt_identity':identity,'prompt_sha256':module.digest(identity)}
            module.verify_prompt(root,plan)
            (root/paths[0]).write_text('changed instructions')
            with self.assertRaises(ValueError):module.verify_prompt(root,plan)

    def test_empty_prompt_manifest_is_rejected(self):
        identity={'scheme':'reader-prompt-files-v1','files':{}}
        with self.assertRaises(ValueError):module.verify_prompt(Path('.'),{'prompt_identity':identity,'prompt_sha256':module.digest(identity)})

    def test_git_checkout_requires_exact_clean_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            (root/'tracked.txt').write_text('one')
            subprocess.run(['git','add','tracked.txt'],cwd=root,check=True)
            subprocess.run(['git','-c','user.name=Benchmark Test','-c','user.email=test@example.invalid','commit','-qm','initial'],cwd=root,check=True)
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            self.assertEqual(module.verify_git_checkout(root,commit,'Benchmark'),commit)
            with self.assertRaises(SystemExit):module.verify_git_checkout(root,None,'Benchmark')
            with self.assertRaises(SystemExit):module.verify_git_checkout(root,'0'*40,'Benchmark')
            (root/'tracked.txt').write_text('dirty')
            with self.assertRaises(SystemExit):module.verify_git_checkout(root,commit,'Benchmark')

    def test_untracked_private_inputs_do_not_dirty_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            (root/'tracked.txt').write_text('one')
            subprocess.run(['git','add','tracked.txt'],cwd=root,check=True)
            subprocess.run(['git','-c','user.name=Benchmark Test','-c','user.email=test@example.invalid','commit','-qm','initial'],cwd=root,check=True)
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
            (root/'private-corpus.zip').write_text('not tracked')
            self.assertEqual(module.verify_git_checkout(root,commit,'Benchmark'),commit)
