# lock_account

Fleet-wide Oracle account lock helper. Given an **LDAP** username
(`firstname.lastname`), it maps it to the Oracle form (upper-case, dot → underscore —
`alireza.aghaja` → `ALIREZA_AGHAJA`) and locks that account across every database in the
target list.

| File | Purpose |
|---|---|
| `lock_account.sh` | The worker. Takes one LDAP username, walks `PRODUCTIONLIST` / `UATLIST` / `IATLIST`, and locks the matching Oracle user on each. Logs per run to `logs/<timestamp>_<ORACLE_USER>.log`. |
| `lock_acc.bashrc` | Shell profile fragment for the Oracle account — defines `cdlock` and the `lockacc` function, which validates the username format and loops `lock_account.sh` over several users, printing a success/failure summary. |

## Deployment

Both files run **on the Oracle hosts**, not from this repo:

- script home: `/oracle/alireza/script/lock_account_dir`
- DB lists: `/oracle/alireza/script/dblist/{PRODUCTIONLIST,UATLIST,IATLIST}`
- Oracle home: `/oracle/product/19.13/db_1`

## Credentials

The script connects as `monitoruser` and reads its password from the **`ORACLE_PASSWORD`
environment variable** — it is not stored in the file. Export it in the calling shell
before running.

## Usage

```bash
lockacc alireza.aghaja                      # one user
lockacc alireza.aghaja maryam.mare          # several, sequentially
```

The username must be a valid LDAP form (`>=2 chars` . `>=1 char`); anything else is
rejected before any database is touched.
