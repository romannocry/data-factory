import pandas as pd
from dataclasses import dataclass, field
from typing import Any, Union
from datetime import datetime, timezone
import json


# ======================================================================== #
#  Data classes – the change object hierarchy                               #
# ======================================================================== #

@dataclass
class FieldChange:
    """A single field that changed value within an updated row."""
    field:          str
    previous_value: Any
    current_value:  Any

    def to_dict(self) -> dict:
        return {
            "field":          self.field,
            "previous_value": self.previous_value,
            "current_value":  self.current_value,
        }


@dataclass
class RowChange:
    """
    Represents one changed row.

    operation          : "update" | "insert" | "delete"
    primary_key_values : e.g. {"id": 42} or {"first_name": "Alice", "last_name": "Smith"}
    field_changes      : populated only for "update" operations (listened_fields only)
    row_data           : snapshot restricted to output_fields
                         (new state for update/insert, old state for delete)
    """
    operation:          str
    primary_key_values: dict[str, Any]
    field_changes:      list[FieldChange] = field(default_factory=list)
    row_data:           dict[str, Any]    = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "operation":          self.operation,
            "primary_key_values": self.primary_key_values,
            "field_changes":      [fc.to_dict() for fc in self.field_changes],
            "row_data":           self.row_data,
        }


@dataclass
class ChangeReport:
    """
    Top-level object returned by compare_dataframes.
    Ready to serialise and POST to your API.
    """
    generated_at:    str             = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    primary_key:     list[str]       = field(default_factory=list)
    listened_fields: list[str]       = field(default_factory=list)
    output_fields:   list[str]       = field(default_factory=list)
    changes:         list[RowChange] = field(default_factory=list)

    # ── Convenience filters ───────────────────────────────────────────
    @property
    def updates(self)     -> list[RowChange]: return [c for c in self.changes if c.operation == "update"]
    @property
    def inserts(self)     -> list[RowChange]: return [c for c in self.changes if c.operation == "insert"]
    @property
    def deletes(self)     -> list[RowChange]: return [c for c in self.changes if c.operation == "delete"]
    @property
    def has_changes(self) -> bool:            return bool(self.changes)

    def to_dict(self) -> dict:
        return {
            "generated_at":    self.generated_at,
            "primary_key":     self.primary_key,
            "listened_fields": self.listened_fields,
            "output_fields":   self.output_fields,
            "summary": {
                "total":    len(self.changes),
                "updated":  len(self.updates),
                "inserted": len(self.inserts),
                "deleted":  len(self.deletes),
            },
            "changes": [c.to_dict() for c in self.changes],
        }

    def to_json(self, indent: int = 2) -> str:
        def _sanitise(obj):
            """Recursively replace NaN/Inf with None so the output is valid JSON."""
            if isinstance(obj, float) and (obj != obj or obj == float("inf") or obj == float("-inf")):
                return None
            if isinstance(obj, dict):
                return {k: _sanitise(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitise(v) for v in obj]
            return obj

        return json.dumps(_sanitise(self.to_dict()), indent=indent, default=str)

    def to_csv(self) -> str:
        """
        Flatten the report into a CSV string.

        One row per changed field for updates (so a row with 3 field changes
        produces 3 CSV lines). One row per record for inserts and deletes
        (changed_field / previous_value / current_value are left blank).

        Columns:
          generated_at | operation | <pk cols> | changed_field |
          previous_value | current_value | <output_fields>
        """
        import csv, io, math

        def _clean(v):
            """Replace NaN/Inf with empty string for CSV output."""
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return ""
            return v if v is not None else ""

        pk_cols      = self.primary_key
        output_cols  = self.output_fields
        meta_cols    = ["generated_at", "operation"]
        diff_cols    = ["changed_field", "previous_value", "current_value"]
        header       = meta_cols + pk_cols + diff_cols + output_cols

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)

        for rc in self.changes:
            # Base fields shared by every row of this change
            base_meta    = [self.generated_at, rc.operation]
            base_pk      = [rc.primary_key_values.get(k, "") for k in pk_cols]
            base_output  = [_clean(rc.row_data.get(c, "")) for c in output_cols]

            if rc.operation == "update" and rc.field_changes:
                # One CSV row per changed field
                for fc in rc.field_changes:
                    writer.writerow(
                        base_meta
                        + base_pk
                        + [fc.field, _clean(fc.previous_value), _clean(fc.current_value)]
                        + base_output
                    )
            else:
                # Insert / delete — no field-level diff
                writer.writerow(base_meta + base_pk + ["", "", ""] + base_output)

        return buf.getvalue()

    def print_log(self) -> None:
        """Human-readable console log."""
        if not self.has_changes:
            print("The two CSV files are identical. No differences found.")
            return

        print("The two CSV files are different. Analysing changes...\n")
        print(f"Listened fields : {', '.join(self.listened_fields)}")
        print(f"Output fields   : {', '.join(self.output_fields)}\n")

        # Updates
        if self.updates:
            for rc in self.updates:
                pk_label = ", ".join(f"{k}={v!r}" for k, v in rc.primary_key_values.items())
                print(f"[UPDATED]  {pk_label}")
                for fc in rc.field_changes:
                    if fc.previous_value == "<column added>":
                        print(f"           {fc.field}: <column added>  →  {fc.current_value!r}")
                    elif fc.current_value == "<column removed>":
                        print(f"           {fc.field}: {fc.previous_value!r}  →  <column removed>")
                    else:
                        print(f"           {fc.field}: {fc.previous_value!r}  →  {fc.current_value!r}")
                print()
        else:
            print("No updated rows detected.\n")

        # Inserts
        if self.inserts:
            print(f"{'─'*60}")
            print(f"INSERTED ROWS ({len(self.inserts)} row(s)):")
            print(f"{'─'*60}")
            for rc in self.inserts:
                pk_label = ", ".join(f"{k}={v!r}" for k, v in rc.primary_key_values.items())
                values   = ", ".join(f"{c}={v!r}" for c, v in rc.row_data.items())
                print(f"[INSERTED] {pk_label}  |  {values}")
            print()
        else:
            print("No inserted rows detected.\n")

        # Deletes
        if self.deletes:
            print(f"{'─'*60}")
            print(f"DELETED ROWS ({len(self.deletes)} row(s)):")
            print(f"{'─'*60}")
            for rc in self.deletes:
                pk_label = ", ".join(f"{k}={v!r}" for k, v in rc.primary_key_values.items())
                values   = ", ".join(f"{c}={v!r}" for c, v in rc.row_data.items())
                print(f"[DELETED]  {pk_label}  |  {values}")
            print()
        else:
            print("No deleted rows detected.\n")

        # Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Updated  : {len(self.updates)}")
        print(f"  Inserted : {len(self.inserts)}")
        print(f"  Deleted  : {len(self.deletes)}")
        print("=" * 60)


# ======================================================================== #
#  Validation helpers                                                       #
# ======================================================================== #

def _validate_primary_key(
    primary_key: list[str],
    df1: pd.DataFrame,
    df2: pd.DataFrame,
) -> None:
    """
    Raise a descriptive ValueError when any primary key column is missing
    from df1, df2, or both, listing what is available in each frame.
    """
    missing_in_df1 = [c for c in primary_key if c not in df1.columns]
    missing_in_df2 = [c for c in primary_key if c not in df2.columns]

    if missing_in_df1 or missing_in_df2:
        raise ValueError(
            f"\n[primary_key] Invalid column(s) detected."
            f"\n  Requested            : {primary_key}"
            + (f"\n  Missing from df1     : {missing_in_df1}" if missing_in_df1 else "")
            + (f"\n  Missing from df2     : {missing_in_df2}" if missing_in_df2 else "")
            + f"\n  Available in df1     : {sorted(df1.columns.tolist())}"
            + f"\n  Available in df2     : {sorted(df2.columns.tolist())}"
        )


def _normalise_field_list(
    param: Union[str, list[str], None],
    fallback_cols: set[str],
    param_name: str,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
) -> list[str]:
    """
    Normalise a field-list parameter and validate every column against both
    DataFrames.  On failure, raise a descriptive ValueError that includes:
      - which columns were requested
      - which ones are missing from both frames
      - which columns are actually available in each frame

    Columns present in only one of the two frames are allowed (they represent
    added/removed columns) but emit a WARNING so the caller is aware.
    """
    if param is None:
        return sorted(fallback_cols)
    if isinstance(param, str):
        param = [param]

    # A column is truly unknown only if absent from BOTH frames
    unknown = [c for c in param if c not in df1.columns and c not in df2.columns]
    if unknown:
        raise ValueError(
            f"\n[{param_name}] Invalid column(s) detected."
            f"\n  Requested                     : {param}"
            f"\n  Not found in either DataFrame : {unknown}"
            f"\n  Available in df1              : {sorted(df1.columns.tolist())}"
            f"\n  Available in df2              : {sorted(df2.columns.tolist())}"
        )

    # Non-fatal: column exists in only one frame (added or removed between snapshots)
    only_in_df1 = [c for c in param if c in df1.columns and c not in df2.columns]
    only_in_df2 = [c for c in param if c not in df1.columns and c in df2.columns]
    if only_in_df1:
        print(f"[WARNING] [{param_name}] column(s) present only in df1 (will be treated as removed): {only_in_df1}")
    if only_in_df2:
        print(f"[WARNING] [{param_name}] column(s) present only in df2 (will be treated as added)  : {only_in_df2}")

    return param


# ======================================================================== #
#  Core comparison function                                                 #
# ======================================================================== #

def compare_dataframes(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    primary_key: Union[str, list[str]],
    listened_fields: Union[str, list[str], None] = None,
    output_fields:   Union[str, list[str], None] = None,
) -> ChangeReport:
    """
    Compare two DataFrames based on a primary key (one or many fields).

    Returns a ChangeReport object containing all detected changes
    (updates, inserts, deletes), ready to serialise and send to an API.

    Args:
        df1              : The "before" DataFrame (original / old state).
        df2              : The "after"  DataFrame (new / updated state).
        primary_key      : Column name (str) or list of column names (list[str])
                           that uniquely identify each row.
        listened_fields  : Fields to watch for value changes.
                           Only changes in these fields produce a FieldChange entry
                           and trigger an "update" row in the report.
                           Defaults to None → all non-key fields are watched.
        output_fields    : Fields to include in row_data for every change
                           (update / insert / delete).
                           Use this for fields you want in the payload but don't
                           need to diff (e.g. "email" — carry it along, skip the
                           comparison work).
                           Defaults to None → same set as listened_fields.
                           listened_fields are always included automatically.

    Raises:
        TypeError  : if df1/df2 are not DataFrames, or field args are the wrong type.
        ValueError : if any primary_key, listened_fields, or output_fields column
                     cannot be found in either DataFrame (with full context).
    """
    try:
        # ------------------------------------------------------------------ #
        #  Type guards                                                        #
        # ------------------------------------------------------------------ #
        if not isinstance(df1, pd.DataFrame):
            raise TypeError(f"df1 must be a pandas DataFrame, got {type(df1).__name__!r}.")
        if not isinstance(df2, pd.DataFrame):
            raise TypeError(f"df2 must be a pandas DataFrame, got {type(df2).__name__!r}.")

        for name, val in [("primary_key", primary_key),
                          ("listened_fields", listened_fields),
                          ("output_fields", output_fields)]:
            if val is not None and not isinstance(val, (str, list)):
                raise TypeError(
                    f"{name!r} must be a str, list[str], or None — got {type(val).__name__!r}."
                )

        if df1.empty and df2.empty:
            print("[WARNING] Both DataFrames are empty. Nothing to compare.")
            return ChangeReport()

        # ------------------------------------------------------------------ #
        #  Normalise & validate primary_key                                   #
        # ------------------------------------------------------------------ #
        if isinstance(primary_key, str):
            primary_key = [primary_key]

        _validate_primary_key(primary_key, df1, df2)

        # ------------------------------------------------------------------ #
        #  Normalise & validate listened_fields and output_fields             #
        # ------------------------------------------------------------------ #
        non_key_cols = (set(df1.columns) | set(df2.columns)) - set(primary_key)
        print(f"[INFO] Non-key columns available for listening/output: {sorted(non_key_cols)}")

        listened_fields = _normalise_field_list(
            listened_fields, non_key_cols, "listened_fields", df1, df2
        )

        # output_fields defaults to listened_fields; listened_fields are always
        # merged in so the diff context is never missing from the payload.
        if output_fields is None:
            output_fields = listened_fields
        else:
            output_fields = _normalise_field_list(
                output_fields, non_key_cols, "output_fields", df1, df2
            )
            extra = [c for c in output_fields if c not in listened_fields]
            output_fields = listened_fields + extra

        report = ChangeReport(
            primary_key=primary_key,
            listened_fields=listened_fields,
            output_fields=output_fields,
        )

        # Quick exit if identical
        if df1.equals(df2):
            return report

        # ------------------------------------------------------------------ #
        #  Index on primary key                                               #
        # ------------------------------------------------------------------ #
        df1_indexed = df1.set_index(primary_key)
        df2_indexed = df2.set_index(primary_key)

        idx1 = set(df1_indexed.index)
        idx2 = set(df2_indexed.index)

        common_keys   = idx1 & idx2
        inserted_keys = idx2 - idx1
        deleted_keys  = idx1 - idx2

        def key_to_dict(key) -> dict[str, Any]:
            values = key if isinstance(key, tuple) else (key,)
            return dict(zip(primary_key, values))

        def extract_row(row: pd.Series, cols: list[str]) -> dict[str, Any]:
            return {c: row[c] for c in cols if c in row.index}

        # ------------------------------------------------------------------ #
        #  1. UPDATES  — diffing limited to listened_fields                   #
        # ------------------------------------------------------------------ #
        for key in sorted(common_keys):
            row1 = df1_indexed.loc[key]
            row2 = df2_indexed.loc[key]
            if not isinstance(row1, pd.Series): row1 = row1.iloc[0]
            if not isinstance(row2, pd.Series): row2 = row2.iloc[0]

            watch_cols   = [c for c in listened_fields if c in row1.index and c in row2.index]
            added_cols   = [c for c in listened_fields if c not in row1.index and c in row2.index]
            removed_cols = [c for c in listened_fields if c in row1.index and c not in row2.index]

            field_changes: list[FieldChange] = []

            for col in watch_cols:
                v1, v2 = row1[col], row2[col]
                both_nan = pd.isna(v1) and pd.isna(v2)
                if not both_nan and v1 != v2:
                    field_changes.append(FieldChange(field=col, previous_value=v1, current_value=v2))

            for col in added_cols:
                field_changes.append(FieldChange(field=col, previous_value="<column added>", current_value=row2[col]))

            for col in removed_cols:
                field_changes.append(FieldChange(field=col, previous_value=row1[col], current_value="<column removed>"))

            if field_changes:
                report.changes.append(RowChange(
                    operation="update",
                    primary_key_values=key_to_dict(key),
                    field_changes=field_changes,
                    row_data=extract_row(row2, output_fields),
                ))

        # ------------------------------------------------------------------ #
        #  2. INSERTS                                                         #
        # ------------------------------------------------------------------ #
        for key in sorted(inserted_keys):
            row = df2_indexed.loc[key]
            if not isinstance(row, pd.Series): row = row.iloc[0]
            report.changes.append(RowChange(
                operation="insert",
                primary_key_values=key_to_dict(key),
                row_data=extract_row(row, output_fields),
            ))

        # ------------------------------------------------------------------ #
        #  3. DELETES                                                         #
        # ------------------------------------------------------------------ #
        for key in sorted(deleted_keys):
            row = df1_indexed.loc[key]
            if not isinstance(row, pd.Series): row = row.iloc[0]
            report.changes.append(RowChange(
                operation="delete",
                primary_key_values=key_to_dict(key),
                row_data=extract_row(row, output_fields),
            ))

        return report

    except (TypeError, ValueError):
        # Re-raise configuration errors as-is — they already have clear messages
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected error during DataFrame comparison: {exc}"
        ) from exc


# ======================================================================== #
#  Entry point                                                              #
# ======================================================================== #
if __name__ == "__main__":
    file1 = "old.csv"
    file2 = "new.csv"

    df_previous = pd.read_csv(file1)
    df_current = pd.read_csv(file2)

    report = compare_dataframes(
        df_previous, df_current,
        primary_key=["id"],
        # Diff is computed only on these fields:
        listened_fields=["officer", "department"],
        # These extra fields are carried in row_data but never diffed:
        output_fields=["id","email", "name","last_read"],
    )

    # Human-readable log
    #report.print_log()

    # ── JSON output (nested, ideal for REST APIs) ─────────────────────
    print("\n--- JSON payload ---")
    #print(report.to_json())

    # ── CSV output (flat, ideal for DB bulk-insert or spreadsheet) ────
    print("\n--- CSV payload ---")
    print(report.to_csv())

    # ── Save to file ──────────────────────────────────────────────────
    # with open("changes.json", "w") as f:
    #     f.write(report.to_json())

    # with open("changes.csv", "w", newline="") as f:
    #     f.write(report.to_csv())