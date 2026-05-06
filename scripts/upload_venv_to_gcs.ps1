# ============================================================================
# upload_venv_to_gcs.ps1 - Upload portable code-puppy venv zip to GCS
# ============================================================================
# Uses the GCS JSON REST API directly - no gcloud SDK needed.
# Authenticates via service account JWT -> OAuth2 access token.
# Lifted from puppy-launcher/scripts/upload_to_gcs.ps1.
#
# Uploads to:
#   gs://<bucket>/code-puppy-venv/<version>/code-puppy-venv-<platform>.zip
# When -WriteLatest is passed, also writes:
#   gs://<bucket>/code-puppy-venv/latest/version.txt   (no trailing newline)
# Only call -WriteLatest after BOTH platform uploads have succeeded so the
# pointer never lies.
# ============================================================================

param(
    [Parameter(Mandatory)]
    [string]$ZipPath,

    [Parameter(Mandatory)]
    [string]$Version,

    [Parameter(Mandatory)]
    [string]$SaKeyBase64,

    [string]$BucketName = "puppy-pages",

    [string]$Platform = "windows",

    [switch]$WriteLatest
)

$ErrorActionPreference = "Stop"

# ---------- Validate inputs ----------
if (-not (Test-Path $ZipPath)) {
    Write-Error "Zip not found at: $ZipPath"
    exit 1
}

$zipSize = (Get-Item $ZipPath).Length
Write-Host "Zip      : $ZipPath ($([math]::Round($zipSize / 1MB, 2)) MB)"
Write-Host "Version  : $Version"
Write-Host "Bucket   : $BucketName"
Write-Host "Platform : $Platform"

# ---------- Decode SA key ----------
Write-Host "Decoding service account key..."
# Strip ALL whitespace before decoding. The encrypted env var pipeline
# (Looper -> agent -> $env -> here) sometimes inserts CR/LF or padding
# spaces, and FromBase64String is strict about both. -replace '\s' nukes
# spaces, tabs, CR, LF in one shot.
$saKeyB64Clean = $SaKeyBase64 -replace '\s', ''

# DIAGNOSTIC: Looper encrypts secrets as `ENC[...]`. If the agent didn't
# decrypt it (suspected on the vs2022 image), we'd see ENC[ here. Print
# safe head/tail bytes + length so we can see WHAT is wrong without
# leaking the actual secret.
$len = $saKeyB64Clean.Length
$head = if ($len -ge 8) { $saKeyB64Clean.Substring(0, 8) } else { $saKeyB64Clean }
$tail = if ($len -ge 8) { $saKeyB64Clean.Substring($len - 8) } else { '' }
Write-Host "DIAG: SaKeyBase64 length=$len head='$head' tail='$tail' (mod4=$($len % 4))"

# Looper's ENC[...] decryption is inconsistent across platforms: Linux
# agents expose the value still-base64-encoded, but Windows vs2022 agents
# decode it one extra hop and hand us the raw JSON. Detect either format
# by sniffing the first non-whitespace char: '{' => already JSON, else
# treat as base64 and decode.
if ($saKeyB64Clean.StartsWith('{')) {
    Write-Host "DIAG: env var contains raw JSON (Windows-style); skipping base64 decode"
    $saKeyJson = $saKeyB64Clean
} else {
    Write-Host "DIAG: env var contains base64; decoding"
    $saKeyJson = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String($saKeyB64Clean)
    )
}
$saKey = $saKeyJson | ConvertFrom-Json
if (-not $saKey.client_email) {
    Write-Error "SA key JSON is missing client_email"
    exit 1
}
Write-Host "Service account: $($saKey.client_email)"

# ---------- JWT helpers ----------
function Get-Base64Url([byte[]]$bytes) {
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-GcsAccessToken($saKey) {
    $now = [int][double]::Parse(
        (Get-Date -Date ((Get-Date).ToUniversalTime()) -UFormat %s)
    )

    $header = '{"alg":"RS256","typ":"JWT"}'
    $headerB64 = Get-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($header))

    $claims = @{
        iss   = $saKey.client_email
        scope = "https://www.googleapis.com/auth/devstorage.read_write"
        aud   = "https://oauth2.googleapis.com/token"
        iat   = $now
        exp   = $now + 3600
    } | ConvertTo-Json -Compress
    $claimsB64 = Get-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($claims))

    $unsigned = "$headerB64.$claimsB64"
    $pemRaw = $saKey.private_key
    # Defensive strip: nuke EVERYTHING that isn't in the base64 alphabet.
    # When the SA JSON arrives via Windows env var, the `\n` escapes inside
    # `private_key` may be literal backslash-n (not newlines), and the BEGIN/
    # END markers contain `-`. One regex kills all of it: PEM headers,
    # newlines, literal `\n`, whitespace -- leaving pure base64.
    $pemStripped = $pemRaw -replace '[^A-Za-z0-9+/=]', ''
    Write-Host "DIAG: pemStripped length=$($pemStripped.Length) (mod4=$($pemStripped.Length % 4))"
    $keyBytes = [Convert]::FromBase64String($pemStripped)

    $cngKey = [System.Security.Cryptography.CngKey]::Import(
        $keyBytes,
        [System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob
    )
    $rsa = New-Object System.Security.Cryptography.RSACng($cngKey)
    $sigBytes = $rsa.SignData(
        [System.Text.Encoding]::UTF8.GetBytes($unsigned),
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
    $sigB64 = Get-Base64Url $sigBytes
    $jwt = "$unsigned.$sigB64"

    $tokenResponse = Invoke-RestMethod `
        -Uri "https://oauth2.googleapis.com/token" `
        -Method POST `
        -ContentType "application/x-www-form-urlencoded" `
        -Body "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=$jwt" `
        -Proxy "http://sysproxy.wal-mart.com:8080"

    return $tokenResponse.access_token
}

Write-Host "Obtaining GCS access token..."
$accessToken = Get-GcsAccessToken $saKey
if (-not $accessToken) {
    Write-Error "Failed to obtain access token"
    exit 1
}
Write-Host "Access token obtained."

# ---------- Upload helper ----------
function Upload-ToBucket($filePath, $bucketName, $objectName, $token, $contentType) {
    if (-not $contentType) { $contentType = "application/octet-stream" }
    $encodedObject = [System.Uri]::EscapeDataString($objectName)
    $uri = "https://storage.googleapis.com/upload/storage/v1/b/$bucketName/o?uploadType=media&name=$encodedObject"

    $fileBytes = [System.IO.File]::ReadAllBytes($filePath)

    Write-Host "Uploading to gs://$bucketName/$objectName ..."
    $response = Invoke-RestMethod `
        -Uri $uri `
        -Method POST `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType $contentType `
        -Body $fileBytes `
        -Proxy "http://sysproxy.wal-mart.com:8080"

    Write-Host "  OK - size: $($response.size) bytes"
}

# ---------- Upload the zip ----------
$zipObject = "code-puppy-venv/$Version/code-puppy-venv-$Platform.zip"
Upload-ToBucket $ZipPath $BucketName $zipObject $accessToken "application/zip"

# ---------- Optionally write latest/version.txt ----------
if ($WriteLatest) {
    $versionTmpFile = Join-Path $env:TEMP "version.txt"
    # NoNewline ensures the file contains exactly the version string, no trailing \n
    $Version | Out-File -FilePath $versionTmpFile -Encoding ASCII -NoNewline
    Upload-ToBucket $versionTmpFile $BucketName "code-puppy-venv/latest/version.txt" $accessToken "text/plain"
    Remove-Item $versionTmpFile -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Upload complete ==="
Write-Host "  Version  : $Version"
Write-Host "  Bucket   : $BucketName"
Write-Host "  Platform : $Platform"
if ($WriteLatest) { Write-Host "  Latest pointer updated." }
