from pathlib import Path

import pytest

from statconvert.batch import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SKIPPED,
    BatchError,
    build_batch_plan,
    discover_input_files,
    normalize_target_extension,
)


def test_normalize_target_extension_adds_dot():

    assert normalize_target_extension(
        "csv"
    ) == ".csv"


def test_normalize_target_extension_keeps_dot():

    assert normalize_target_extension(
        ".csv"
    ) == ".csv"


def test_normalize_target_extension_lowercases():

    assert normalize_target_extension(
        "CSV"
    ) == ".csv"


def test_normalize_target_extension_rejects_unsupported():

    with pytest.raises(
        BatchError,
        match="Unsupported target format",
    ):
        normalize_target_extension(
            "unsupported"
        )


def test_discover_input_files_single_file_returns_one_file(tmp_path):

    input_file = _touch(
        tmp_path / "survey.sav"
    )

    assert discover_input_files(
        input_file
    ) == [
        input_file,
    ]


def test_discover_input_files_non_recursive_returns_direct_files_only(tmp_path):

    direct = _touch(
        tmp_path / "direct.sav"
    )
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    _touch(
        nested_dir / "nested.sav"
    )

    assert discover_input_files(
        tmp_path,
        recursive=False,
    ) == [
        direct,
    ]


def test_discover_input_files_recursive_returns_nested_files(tmp_path):

    direct = _touch(
        tmp_path / "direct.sav"
    )
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested = _touch(
        nested_dir / "nested.sav"
    )

    assert discover_input_files(
        tmp_path,
        recursive=True,
    ) == [
        direct,
        nested,
    ]


def test_discover_input_files_missing_path_raises(tmp_path):

    with pytest.raises(
        BatchError,
        match="Input path does not exist",
    ):
        discover_input_files(
            tmp_path / "missing"
        )


def test_discover_input_files_include_patterns_work(tmp_path):

    sav = _touch(
        tmp_path / "survey.sav"
    )
    _touch(
        tmp_path / "notes.txt"
    )

    assert discover_input_files(
        tmp_path,
        patterns=[
            "*.sav",
        ],
    ) == [
        sav,
    ]


def test_discover_input_files_exclude_patterns_work(tmp_path):

    keep = _touch(
        tmp_path / "keep.sav"
    )
    _touch(
        tmp_path / "skip.tmp"
    )

    assert discover_input_files(
        tmp_path,
        exclude_patterns=[
            "*.tmp",
        ],
    ) == [
        keep,
    ]


def test_discover_input_files_results_are_sorted(tmp_path):

    b_file = _touch(
        tmp_path / "b.sav"
    )
    a_file = _touch(
        tmp_path / "a.sav"
    )

    assert discover_input_files(
        tmp_path
    ) == [
        a_file,
        b_file,
    ]


def test_batch_plan_workload_counts_unique_files_and_input_bytes(tmp_path):
    first = _touch(tmp_path / "input" / "first.sav")
    second = _touch(tmp_path / "input" / "second.sav")
    first.write_bytes(b"1234")
    second.write_bytes(b"123456")

    plan = build_batch_plan(
        tmp_path / "input",
        tmp_path / "output",
        "csv",
        workers=2,
        transform_enabled=True,
        validation_enabled=True,
        object_mode="object",
    )

    assert plan.workload.planned_items == 2
    assert plan.workload.planned_files == 2
    assert plan.workload.supported_files == 2
    assert plan.workload.skipped_files == 0
    assert plan.workload.total_input_bytes == 10
    assert plan.workload.largest_input_file_bytes == 6
    assert plan.workload.workers == 2
    assert plan.workload.transform_enabled is True
    assert plan.workload.validation_enabled is True
    assert plan.workload.object_mode == "object"
    assert "reduce --workers" in (plan.workload.memory_note or "")


def test_discovery_includes_hidden_files_and_excludes_office_temp_files(tmp_path):
    hidden = _touch(tmp_path / ".hidden.sav")
    _touch(tmp_path / "~$survey.xlsx")

    assert discover_input_files(
        tmp_path,
        exclude_patterns=["~$*"],
    ) == [hidden]


def test_relative_include_and_exclude_patterns_apply_in_order(tmp_path):
    keep = _touch(tmp_path / "2024" / "keep.sav")
    _touch(tmp_path / "2024" / "archive" / "old.sav")
    _touch(tmp_path / "2025" / "other.dta")

    assert discover_input_files(
        tmp_path,
        recursive=True,
        patterns=["**/*.sav"],
        exclude_patterns=["**/archive/*"],
    ) == [keep]


def test_recursive_plan_does_not_rediscover_nested_output_tree(tmp_path):
    input_dir = tmp_path / "input"
    source = _touch(input_dir / "source.csv")
    _touch(input_dir / "generated" / "old.csv")

    plan = build_batch_plan(
        input_dir,
        input_dir / "generated",
        "csv",
        recursive=True,
    )

    assert [item.input_file for item in plan.items] == [source]


def test_build_batch_plan_single_file_to_output_directory(tmp_path):

    input_file = _touch(
        tmp_path / "input" / "survey.sav"
    )
    output_dir = tmp_path / "output"

    plan = build_batch_plan(
        input_file,
        output_dir,
        "csv",
    )
    item = plan.items[0]

    assert item.output_file == output_dir / "survey.csv"
    assert item.status == BATCH_STATUS_PENDING
    assert item.relative_path == Path(
        "survey.sav"
    )


def test_build_batch_plan_single_file_to_explicit_output_file(tmp_path):

    input_file = _touch(
        tmp_path / "survey.sav"
    )
    output_file = tmp_path / "converted" / "custom.csv"

    plan = build_batch_plan(
        input_file,
        output_file,
        "csv",
    )

    assert plan.items[0].output_file == output_file


def test_single_file_explicit_output_suffix_must_match_target(tmp_path):
    input_file = _touch(tmp_path / "survey.sav")

    with pytest.raises(
        BatchError,
        match="Explicit output file extension does not match --to format",
    ):
        build_batch_plan(input_file, tmp_path / "survey.csv", "parquet")


def test_directory_input_rejects_output_path_with_suffix(tmp_path):
    input_dir = tmp_path / "input"
    _touch(input_dir / "survey.sav")

    with pytest.raises(
        BatchError,
        match="output path must be a directory path",
    ):
        build_batch_plan(input_dir, tmp_path / "output.csv", "csv")


def test_build_batch_plan_directory_outputs_to_output_directory(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(
        input_dir / "survey.sav"
    )

    plan = build_batch_plan(
        input_dir,
        output_dir,
        ".csv",
    )

    assert plan.items[0].output_file == output_dir / "survey.csv"


def test_build_batch_plan_recursive_preserves_structure(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(
        input_dir / "a" / "survey.sav"
    )

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
        recursive=True,
        preserve_structure=True,
    )

    assert plan.items[0].output_file == output_dir / "a" / "survey.csv"
    assert plan.items[0].relative_path == Path(
        "a"
    ) / "survey.sav"


def test_preserved_structure_avoids_same_stem_collisions(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(input_dir / "2024" / "survey.sav")
    _touch(input_dir / "2025" / "survey.sav")

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
        recursive=True,
        preserve_structure=True,
    )

    assert plan.blocked_count == 0
    assert [item.relative_path.as_posix() for item in plan.items] == [
        "2024/survey.sav",
        "2025/survey.sav",
    ]
    assert [item.output_file for item in plan.items] == [
        output_dir / "2024" / "survey.csv",
        output_dir / "2025" / "survey.csv",
    ]


def test_build_batch_plan_recursive_can_flatten_outputs(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(
        input_dir / "a" / "survey.sav"
    )

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
        recursive=True,
        preserve_structure=False,
    )

    assert plan.items[0].output_file == output_dir / "survey.csv"


def test_build_batch_plan_skips_unsupported_when_included(tmp_path):

    input_dir = tmp_path / "input"
    _touch(
        input_dir / "readme.txt"
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        include_unsupported=True,
    )

    assert plan.items[0].status == BATCH_STATUS_SKIPPED
    assert plan.items[0].reason == "Unsupported input format"
    assert plan.items[0].output_file is None


def test_build_batch_plan_omits_unsupported_when_excluded(tmp_path):

    input_dir = tmp_path / "input"
    _touch(
        input_dir / "survey.sav"
    )
    _touch(
        input_dir / "readme.txt"
    )

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        include_unsupported=False,
    )

    assert plan.total_count == 1
    assert plan.items[0].input_file.name == "survey.sav"


def test_build_batch_plan_defers_existing_output_check_until_execution(tmp_path):

    input_file = _touch(
        tmp_path / "survey.sav"
    )
    output_file = _touch(
        tmp_path / "output" / "survey.csv"
    )

    plan = build_batch_plan(
        input_file,
        output_file.parent,
        "csv",
        overwrite=False,
    )

    assert plan.items[0].status == BATCH_STATUS_PENDING
    assert plan.items[0].reason is None


def test_build_batch_plan_allows_existing_output_with_overwrite(tmp_path):

    input_file = _touch(
        tmp_path / "survey.sav"
    )
    output_file = _touch(
        tmp_path / "output" / "survey.csv"
    )

    plan = build_batch_plan(
        input_file,
        output_file.parent,
        "csv",
        overwrite=True,
    )

    assert plan.items[0].status == BATCH_STATUS_PENDING


def test_build_batch_plan_detects_output_collisions(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(
        input_dir / "a" / "survey.sav"
    )
    _touch(
        input_dir / "b" / "survey.dta"
    )

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
        recursive=True,
        preserve_structure=False,
        overwrite=True,
    )

    assert plan.blocked_count == 2
    assert {
        item.reason
        for item in plan.items
    } == {
        "Output path collision. Use --preserve-structure or choose a different output folder.",
    }


def test_collision_priority_is_not_bypassed_by_overwrite(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(input_dir / "a" / "survey.sav")
    _touch(input_dir / "b" / "survey.dta")
    _touch(output_dir / "survey.csv")

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
        recursive=True,
        preserve_structure=False,
        overwrite=True,
    )

    assert plan.blocked_count == 2
    assert all(
        item.reason
        == "Output path collision. Use --preserve-structure or choose a different output folder."
        for item in plan.items
    )


def test_unsupported_items_do_not_participate_in_collisions(tmp_path):
    input_dir = tmp_path / "input"
    _touch(input_dir / "a" / "survey.sav")
    _touch(input_dir / "b" / "survey.txt")

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        recursive=True,
        preserve_structure=False,
    )

    assert plan.blocked_count == 0
    assert plan.pending_count == 1
    assert plan.skipped_count == 1


def test_unsupported_files_respect_include_patterns(tmp_path):
    input_dir = tmp_path / "input"
    unsupported = _touch(input_dir / "notes.txt")
    _touch(input_dir / "survey.sav")

    plan = build_batch_plan(
        input_dir,
        tmp_path / "output",
        "csv",
        patterns=["*.txt"],
    )

    assert [item.input_file for item in plan.items] == [unsupported]
    assert plan.items[0].status == BATCH_STATUS_SKIPPED


def test_build_batch_plan_blocks_same_input_and_output_path(tmp_path):

    input_file = _touch(
        tmp_path / "survey.csv"
    )

    plan = build_batch_plan(
        input_file,
        input_file,
        "csv",
        overwrite=True,
    )

    assert plan.items[0].status == BATCH_STATUS_BLOCKED
    assert plan.items[0].reason == "Input and output path are the same"


def test_build_batch_plan_empty_directory_raises(tmp_path):

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(
        BatchError,
        match="No input files were discovered",
    ):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
        )


def test_build_batch_plan_all_unsupported_excluded_raises(tmp_path):

    input_dir = tmp_path / "input"
    _touch(
        input_dir / "readme.txt"
    )

    with pytest.raises(
        BatchError,
        match="No supported input files were discovered",
    ):
        build_batch_plan(
            input_dir,
            tmp_path / "output",
            "csv",
            include_unsupported=False,
        )


def test_batch_plan_counts_items_by_status(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _touch(
        input_dir / "pending.sav"
    )
    _touch(
        input_dir / "skipped.txt"
    )
    _touch(
        input_dir / "blocked.dta"
    )
    _touch(
        output_dir / "blocked.csv"
    )

    plan = build_batch_plan(
        input_dir,
        output_dir,
        "csv",
    )

    assert plan.total_count == 3
    assert plan.pending_count == 2
    assert plan.skipped_count == 1
    assert plan.blocked_count == 0
    assert not plan.has_blockers
    assert len(
        plan.pending_items()
    ) == 2
    assert len(
        plan.skipped_items()
    ) == 1
    assert len(
        plan.blocked_items()
    ) == 0


def _touch(
    path: Path
) -> Path:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.touch()

    return path
