"""Registry of external data sources aligned with SciAgent integration tiers."""

from __future__ import annotations

from dataclasses import dataclass

IMMPORT_SOURCE_ID = "immport"
OMICSDI_SOURCE_ID = "omicsdi"
VDJSERVER_SOURCE_ID = "vdjserver"
VIVLI_SOURCE_ID = "vivli"

IMMPORT_REPOSITORY = "ImmPort"


@dataclass(frozen=True)
class SourceRegistryEntry:
    """Metadata for one integrated or planned external data source."""

    id: str
    display_name: str
    source_type: str
    domain: str
    access_profile: str
    implemented: bool
    tool_name: str | None = None
    repository_label: str | None = None
    source_label: str | None = None


SOURCE_REGISTRY: dict[str, SourceRegistryEntry] = {
    IMMPORT_SOURCE_ID: SourceRegistryEntry(
        id=IMMPORT_SOURCE_ID,
        display_name="ImmPort",
        source_type="dataset_repository",
        domain="immunology",
        access_profile="open_or_registered",
        implemented=True,
        tool_name=IMMPORT_SOURCE_ID,
        repository_label=IMMPORT_REPOSITORY,
        source_label="ImmPort",
    ),
    OMICSDI_SOURCE_ID: SourceRegistryEntry(
        id=OMICSDI_SOURCE_ID,
        display_name="OmicsDI",
        source_type="omics_index",
        domain="multi_omics",
        access_profile="mixed",
        implemented=False,
    ),
    VDJSERVER_SOURCE_ID: SourceRegistryEntry(
        id=VDJSERVER_SOURCE_ID,
        display_name="VDJServer",
        source_type="specialized_dataset_repository",
        domain="immune_repertoire",
        access_profile="mixed",
        implemented=False,
    ),
    VIVLI_SOURCE_ID: SourceRegistryEntry(
        id=VIVLI_SOURCE_ID,
        display_name="Vivli / AccessClinicalData@NIAID",
        source_type="clinical_trial_data_repository",
        domain="clinical_trials",
        access_profile="controlled_or_request_based",
        implemented=False,
    ),
}

PLANNED_CONNECTOR_NOTE = "Connector planned; not enabled by default."


def get_source_entry(source_id: str) -> SourceRegistryEntry | None:
    return SOURCE_REGISTRY.get(source_id)


def list_source_entries() -> list[SourceRegistryEntry]:
    return list(SOURCE_REGISTRY.values())


def implemented_dataset_repositories() -> list[SourceRegistryEntry]:
    """Return implemented sources that participate in the dataset discovery pipeline."""
    return [
        entry
        for entry in SOURCE_REGISTRY.values()
        if entry.implemented and entry.repository_label
    ]
