"""The external harness must not relabel a different real prompt."""
import importlib.util
from pathlib import Path
import hashlib
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
