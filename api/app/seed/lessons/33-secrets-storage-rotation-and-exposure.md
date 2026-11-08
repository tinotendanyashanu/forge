+++
slug = "secrets-storage-rotation-and-exposure"
skill = "security"
topic = "secrets"
difficulty = "intermediate"
title = "Secrets: storage, rotation and exposure response"
summary = "Keep credentials within the right trust boundary, distinguish password verification from recoverable credentials, and respond to exposure with revocation rather than cosmetic cleanup."
estimated_minutes = 32
objectives = ["Classify public configuration, credentials and password-verification data.", "Explain why environment injection and redacted representations do not prevent every leak.", "Plan rotation and exposure response around revocation, least privilege and auditable recovery."]
prerequisites = ["security-auth-and-injection", "python-functions-scope-and-closures"]
misconceptions = ["A secret in an environment variable cannot leak.", "Deleting a committed key revokes the provider's credential.", "A frontend build-time environment variable remains private after bundling.", "A fast unsalted hash is appropriate password storage."]
checks = ["sec-frontend-api-key", "sec-password-storage", "sec-leaked-api-key"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; dummy-only executable fixtures and advisory second-model review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "OWASP: Secrets management"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"
[[resources]]
title = "OWASP: Password storage"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"
[[resources]]
title = "OWASP: Logging and data to exclude"
url = "https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html"
[[resources]]
title = "Python 3.12: secrets module"
url = "https://docs.python.org/3.12/library/secrets.html"
+++
## Why it matters

A developer removes an API key from the latest commit and assumes the incident is over. The provider still accepts it, and copies may remain in earlier commits, build artifacts or logs. Another service hides a key from repr output but serializes the whole settings object into an error report. Safe storage is only one part of a credential's lifetime.

Prerequisites: trust boundaries, authentication and ordinary Python function/data behavior. The complete example uses only synthetic values and Python's standard library. It makes no external calls, reads no real environment and never prints the generated token. Do not practice rotation or exposure response against production credentials.

## Mental model

A secret grants a capability. Ask which principal needs it, which resource it authorizes, how broadly it is scoped, how long it remains valid and how it can be revoked. A service endpoint URL is usually configuration; a provider credential used to charge an account is authority. The name API key alone does not tell you whether a provider designed that particular value to be public or secret.

Passwords and outbound credentials have different storage needs. A login service generally needs to verify a password, not recover the original. A service calling a provider may need to retrieve the credential it presents. An application that validates an opaque caller token may instead store a verification hash. Choose the representation from the operation, not from a rule that all secrets must be encrypted or all secrets must be hashed.

Exposure is also different from revocation. Removing one visible copy does not make every copied credential stop working. Revocation changes the authority accepted by the receiving system.

## How it works

Use an approved secret store or deployment injection mechanism, with access limited to the workload and operators that need it. Prefer short-lived workload identity where supported. Environment variables can be a delivery mechanism, but debugging output, crash reports, child processes and overly broad diagnostic endpoints can still expose them. Host administrators and sufficiently privileged or permitted processes may also inspect a workload's environment or memory; restrict that access as part of the trust boundary. Avoid copying credentials into command-line arguments, build output or frontend code.

A browser bundle is delivered to the user. A private provider credential cannot be hidden there by a variable name, minification or a build-time environment file. Put privileged provider access behind an authenticated and authorized backend, or use a provider-designed public/restricted client credential with the intended controls. A backend proxy that accepts arbitrary privileged actions is not a complete solution.

For passwords, use a maintained password-hashing library with a deliberately configured slow, salted algorithm such as Argon2id, following current guidance. Salt is not a secret; it prevents identical passwords from sharing one precomputed verification target. A fast general-purpose hash is not a substitute. Work factors require benchmarking, versioning and rehash-on-success planning. Do not implement a password algorithm from scratch for this exercise.

## Worked example

The mapping stands in for approved server-side configuration injection. The fixture key is visibly a demo value. The class hides it from repr but deliberately shows why that is not a complete serialization policy.

```python
from base64 import urlsafe_b64decode
from dataclasses import asdict, dataclass, field
from secrets import token_urlsafe

@dataclass(frozen=True)
class ServiceConfig:
    endpoint: str
    api_key: str = field(repr=False)

def load_config(values):
    key = values.get("PAYMENT_API_KEY")
    if not key:
        raise ValueError("PAYMENT_API_KEY is required")
    return ServiceConfig("https://payments.example.test", key)

def safe_export(config):
    return {"endpoint": config.endpoint}  # explicit public fields, not an exclusion list

config = load_config({"PAYMENT_API_KEY": "demo-only-not-a-real-credential"})
print(config)
print("api_key" in asdict(config))
print(safe_export(config))
try:
    load_config({})
except ValueError as error:
    print(str(error))

temporary_token = token_urlsafe(32)
decoded = urlsafe_b64decode(temporary_token + "=" * (-len(temporary_token) % 4))
print(len(decoded) == 32)
```

Output:

```text
ServiceConfig(endpoint='https://payments.example.test')
True
{'endpoint': 'https://payments.example.test'}
PAYMENT_API_KEY is required
True
```

The first line avoids an accidental repr leak. The second proves that ordinary dataclass serialization still includes the secret field, even though the example does not print its value. The safe export explicitly selects public fields, so a newly added secret is not exported by default. The missing-configuration error names the required setting without echoing a credential. The generated token uses the secrets module; decoding checks that its representation contains the requested 32 random bytes without printing them. A single token cannot measure generator quality or establish an authorization, expiry or revocation design.

## Common mistakes

- Logging all configuration or outgoing authorization headers to diagnose one failed request.
- Assuming a redacted wrapper, frozen dataclass or secret-looking type prevents every serializer or caller from reading the value.
- Encrypting passwords so operators can recover them instead of storing a password verifier.
- Treating a repository history rewrite as provider revocation. Copies may already exist outside the repository.

## In production

Maintain an inventory of credential owners, scopes, consumers, expiry and rotation procedure. Audit access to the store without recording secret values. A useful log identifies the credential version or key ID when safe, the requesting principal and the operation, not the credential itself. Apply least privilege and separate environments so a test credential cannot silently authorize production actions.

For planned rotation, issue a replacement, update and verify consumers, then retire the old credential according to provider capabilities. Some providers support overlap; others do not, so test the sequence in a nonproduction environment. For a confirmed compromise, revoke or disable the exposed authority promptly rather than delaying containment for a perfectly graceful rollout. Investigate suspicious use and dependent sessions or derived tokens as appropriate.

## Trade-offs and limits

Central secret stores improve policy and auditability but create a dependency that needs availability and recovery planning. Caching credentials reduces lookup load while complicating revocation latency. Short lifetimes reduce exposure windows but require reliable renewal. These are operational contracts, not reasons to fall back to long-lived broad credentials everywhere.

A secret still has to exist somewhere usable during an authorized operation. Reducing access, lifetime and copies limits risk; it does not make memory magically unreadable. Backups, CI artifacts and diagnostic exports need the same classification and retention discipline as primary storage.

## Check your understanding

1. Why is keeping a provider key out of repr insufficient if the code later serializes the whole settings object?
   - Feedback: the serialization path may include fields independently of repr. Define an explicit safe output schema and test it.
2. A key was pushed publicly for one minute and then deleted. What action changes whether it can still authorize requests?
   - Feedback: provider-side revocation or disabling the credential. Deletion removes one copy, not its authority or every other copy.
3. Why might a backend store a recoverable outbound credential but a password verifier instead of the user's password?
   - Feedback: the provider requires presentation of its credential, while login usually requires only verification of a supplied password. Their required operations differ.

The linked FORGE checks cover frontend exposure, password storage and leaked-key response. Use intermediate security assessments for password storage and advanced assessments for exposure handling; the beginner check tests the browser boundary.

## Practice

Using dummy names only, design a safe configuration export and a rotation runbook for two consumers of one provider credential. Test that the export includes endpoint and non-secret version metadata while excluding the key from every output path you control.

Acceptance criteria: missing configuration fails without echoing values; planned rotation includes verification and retirement; compromise response includes revocation and investigation; no real credential is created or changed. Explain how your runbook handles a consumer that still uses the retired version and why rewriting Git history alone cannot finish the incident.
