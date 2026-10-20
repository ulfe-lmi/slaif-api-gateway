"""Audited external-preset migration and rollback against owned PostgreSQL."""

from pathlib import Path

import pytest

from slaif_gateway.modules.clients import registry
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE,
    Codex0162ResponsesClientModule,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file
from slaif_gateway.modules.contracts import ModuleSelectionError
from tests.integration.test_codex_module_upgrade_postgres import (
    _audit_count, _cleanup_key, _mutate_profile, _row_digest, _seed_key,
    _set_client_module, _stored_client_module,
)
from tests.integration.test_lazy_throttling_postgres_redis import owned_pg_url  # noqa: F401,F811


def _facts(module):
    return {'id':module.module_id,'version':module.module_version,'fixture_sha256':module.fixture_sha256}


@pytest.mark.asyncio
@pytest.mark.parametrize('preset',['codex-0.162.1','codex-0.163.0'])
async def test_external_preset_migration_preserves_key_policy_usage_and_rollback(
    owned_pg_url, monkeypatch, preset,  # noqa: F811
):
    module = Codex0162ResponsesClientModule(load_codex_profile_file(
        Path('app/slaif_gateway/modules/clients/profiles')/(preset+'.json')
    ))
    key_id, owner_id, institution_id, cohort_id, _ = await _seed_key(owned_pg_url)
    try:
        await _set_client_module(owned_pg_url,key_id,_facts(CODEX_0162_CLIENT_MODULE))
        before = await _row_digest(owned_pg_url,key_id)
        monkeypatch.setitem(registry._CLIENT_MODULE_REGISTRY_ENTRIES,module.module_id,module)
        # A new preset never silently accepts the previous digest/version.
        with pytest.raises(ModuleSelectionError):
            registry.resolve_responses_client_module({'client_module':_facts(CODEX_0162_CLIENT_MODULE)})
        options = dict(key_id=key_id,from_version=CODEX_0162_CLIENT_MODULE.module_version,
                       from_digest=CODEX_0162_CLIENT_MODULE.fixture_sha256,target='active',
                       action='codex_key_profile_migrated')
        dry = await _mutate_profile(owned_pg_url,**options,apply=False)
        assert dry.status == 'dry_run'
        assert await _row_digest(owned_pg_url,key_id) == before
        assert await _audit_count(owned_pg_url,key_id) == 0
        result = await _mutate_profile(owned_pg_url,**options,apply=True)
        assert result.status == 'applied'
        assert await _row_digest(owned_pg_url,key_id) == before
        assert await _stored_client_module(owned_pg_url,key_id) == _facts(module)
        assert await _audit_count(owned_pg_url,key_id) == 1
        assert registry.resolve_responses_client_module({'client_module':_facts(module)}) is module
        # Rollback uses the same executable with the frozen previous data profile.
        monkeypatch.setitem(registry._CLIENT_MODULE_REGISTRY_ENTRIES,module.module_id,CODEX_0162_CLIENT_MODULE)
        rolled = await _mutate_profile(
            owned_pg_url,key_id=key_id,from_version=module.module_version,
            from_digest=module.fixture_sha256,target='active',
            action='codex_key_profile_migrated',apply=True,
        )
        assert rolled.status == 'applied'
        assert await _row_digest(owned_pg_url,key_id) == before
        assert await _audit_count(owned_pg_url,key_id) == 2
    finally:
        await _cleanup_key(owned_pg_url,key_id=key_id,owner_id=owner_id,
                           institution_id=institution_id,cohort_id=cohort_id)
