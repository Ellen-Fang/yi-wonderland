param([switch]$Reload)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
if (Test-Path -LiteralPath '.venv/Scripts/python.exe') {
    $python = Join-Path $root '.venv/Scripts/python.exe'
} elseif (Test-Path -LiteralPath '.tools/python/python.exe') {
    $python = Join-Path $root '.tools/python/python.exe'
} else {
    $python = 'python'
}
# 由 python-dotenv 讀取設定，避免將 .env 中的金鑰顯示到終端機。
$settings = & $python -c "from dotenv import load_dotenv; import os,json; load_dotenv('.env'); print(json.dumps([os.getenv('HOST','127.0.0.1'),os.getenv('PORT','3000')]))"
if ($LASTEXITCODE -ne 0) { throw '請先安裝 requirements.txt 中的套件。' }
$settings = $settings | ConvertFrom-Json
$uvicornArgs = @('-m','uvicorn','app.main:app','--host',$settings[0],'--port',$settings[1])
if ($Reload) { $uvicornArgs += '--reload' }
& $python @uvicornArgs
exit $LASTEXITCODE
