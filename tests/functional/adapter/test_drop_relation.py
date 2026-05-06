from pathlib import Path

import pytest
from dbt.tests.util import run_dbt


macros__assert_ducklake_drop_relation = """
{% macro assert_drop_explicit_ducklake_relation(schema_name) %}
  {% do run_query("create schema if not exists ducklake_db." ~ schema_name) %}

  {% set relation = api.Relation.create(
      database='ducklake_db',
      schema=schema_name,
      identifier='explicit_drop_target',
      type='table'
  ) %}

  {% do run_query("drop table if exists " ~ relation) %}
  {% do run_query("create table " ~ relation ~ " as select 1 as id") %}
  {% do adapter.drop_relation(relation) %}

  {% set result = run_query(
      "select count(*) from system.information_schema.tables "
      ~ "where table_catalog = 'ducklake_db' "
      ~ "and table_schema = '" ~ schema_name ~ "' "
      ~ "and table_name = 'explicit_drop_target'"
  ) %}
  {% if result.columns[0].values()[0] != 0 %}
    {{ exceptions.raise_compiler_error("explicit DuckLake relation was not dropped") }}
  {% endif %}
{% endmacro %}

{% macro assert_drop_unqualified_ducklake_relation() %}
  {% do run_query("drop table if exists unqualified_drop_target") %}
  {% do run_query("create table unqualified_drop_target as select 1 as id") %}

  {% set relation = api.Relation.create(
      database=none,
      schema=none,
      identifier='unqualified_drop_target',
      type='table'
  ) %}

  {% do adapter.drop_relation(relation) %}

  {% set result = run_query(
      "select count(*) from system.information_schema.tables "
      ~ "where table_catalog = 'ducklake_db' "
      ~ "and table_schema = 'main' "
      ~ "and table_name = 'unqualified_drop_target'"
  ) %}
  {% if result.columns[0].values()[0] != 0 %}
    {{ exceptions.raise_compiler_error("unqualified DuckLake relation was not dropped") }}
  {% endif %}
{% endmacro %}
"""


@pytest.mark.requires_ducklake
@pytest.mark.skip_profile("buenavista", "md")
class TestDucklakeDropRelation:
    @pytest.fixture(scope="class")
    def ducklake_attachment(self, tmp_path_factory):
        root = Path(tmp_path_factory.mktemp("ducklake_drop_relation"))
        metadata_path = root / "metadata.ducklake"
        data_path = root / "data"
        data_path.mkdir(parents=True, exist_ok=True)

        return {
            "path": f"ducklake:sqlite:{metadata_path}",
            "alias": "ducklake_db",
            "options": {"data_path": str(data_path)},
        }

    @pytest.fixture(scope="class")
    def profiles_config_update(self, dbt_profile_target, ducklake_attachment):
        target = dict(dbt_profile_target)
        target["path"] = ":memory:"
        target["database"] = "ducklake_db"
        target["attach"] = [ducklake_attachment]

        settings = dict(target.get("settings", {}))
        settings["schema"] = "ducklake_db.main"
        target["settings"] = settings

        return {
            "test": {
                "outputs": {"dev": target},
                "target": "dev",
            }
        }

    @pytest.fixture(scope="class")
    def macros(self):
        return {"assert_ducklake_drop_relation.sql": macros__assert_ducklake_drop_relation}

    def test_drop_explicit_ducklake_relation_omits_cascade(self, project):
        run_dbt(
            [
                "run-operation",
                "assert_drop_explicit_ducklake_relation",
                "--args",
                f'{{schema_name: "{project.test_schema}"}}',
            ],
            expect_pass=True,
        )

    def test_drop_unqualified_relation_omits_cascade_when_target_is_ducklake(self, project):
        run_dbt(
            ["run-operation", "assert_drop_unqualified_ducklake_relation"],
            expect_pass=True,
        )
