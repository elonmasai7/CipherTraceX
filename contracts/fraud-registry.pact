;; Fraud registry and attestation contracts for Kadena Pact

(define-keyset 'admin-keyset (read-keyset "admin-keyset"))

(module fraud-registry GOVERNANCE
  "Registry for fraud cases, reports, and wallet risk attestations."

  (defcap GOVERNANCE ()
    (enforce-keyset 'admin-keyset))

  (defschema case-schema
    case-id:string
    reporter-hash:string
    metadata-hash:string
    created:time)

  (defschema report-schema
    report-id:string
    case-id:string
    wallet:string
    chain:string
    report-hash:string
    encrypted-hash:string
    created:time)

  (defschema attestation-schema
    wallet:string
    risk-score:decimal
    flags:[string]
    case-ids:[string]
    updated:time)

  (deftable cases:{case-schema})
  (deftable reports:{report-schema})
  (deftable attestations:{attestation-schema})

  (defun create-case (case-id:string reporter-hash:string metadata-hash:string)
    "Create a new fraud case."
    (with-capability (GOVERNANCE)
      (enforce (not (exists cases case-id)) "Case already exists")
      (insert cases case-id
        { "case-id": case-id
        , "reporter-hash": reporter-hash
        , "metadata-hash": metadata-hash
        , "created": (time) })))

  (defun add-report (report-id:string case-id:string wallet:string chain:string report-hash:string encrypted-hash:string)
    "Add a timestamped fraud report linked to a case."
    (with-capability (GOVERNANCE)
      (enforce (exists cases case-id) "Case does not exist")
      (enforce (not (exists reports report-id)) "Report already exists")
      (insert reports report-id
        { "report-id": report-id
        , "case-id": case-id
        , "wallet": wallet
        , "chain": chain
        , "report-hash": report-hash
        , "encrypted-hash": encrypted-hash
        , "created": (time) })))

  (defun attest-wallet (wallet:string risk-score:decimal flags:[string] case-ids:[string])
    "Create or update a wallet risk attestation."
    (with-capability (GOVERNANCE)
      (if (exists attestations wallet)
        (update attestations wallet
          { "risk-score": risk-score
          , "flags": flags
          , "case-ids": case-ids
          , "updated": (time) })
        (insert attestations wallet
          { "wallet": wallet
          , "risk-score": risk-score
          , "flags": flags
          , "case-ids": case-ids
          , "updated": (time) }))))

  (defun get-case (case-id:string)
    "Read a case by ID."
    (read cases case-id))

  (defun get-report (report-id:string)
    "Read a report by ID."
    (read reports report-id))

  (defun get-attestation (wallet:string)
    "Read a wallet attestation."
    (read attestations wallet))
)
