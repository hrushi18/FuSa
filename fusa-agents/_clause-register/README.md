# _clause-register

One YAML per ISO 26262 part. Each entry has a clause **id**, a short **topic** label and a **text**
field. The text field is empty in this repository: ISO 26262 is licensed, so populate it from your
organisation's copy (or point `ClauseRegister` at your internal norm database). Agents cite the id
either way; with text loaded they can also quote the requirement they are satisfying.

Id format: `26262-<part>:<clause>` e.g. `26262-4:6.4.2`. Agents may reference a prefix such as
`26262-4:6` to receive all sub-clauses.
