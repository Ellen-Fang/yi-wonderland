$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$destination = Join-Path $root 'public/cards/rider-waite-smith'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$source = Get-Content (Join-Path $root 'commons-deck.json') -Raw | ConvertFrom-Json
$pages = @($source.query.pages.PSObject.Properties.Value | Sort-Object title)
if ($pages.Count -ne 78) { throw 'Expected 78 cards' }
$majorZh = @('愚者','魔術師','女祭司','皇后','皇帝','教皇','戀人','戰車','力量','隱者','命運之輪','正義','吊人','死神','節制','惡魔','高塔','星星','月亮','太陽','審判','世界')
$ranksEn = @('Ace','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten','Page','Knight','Queen','King')
$ranksZh = @('一','二','三','四','五','六','七','八','九','十','侍者','騎士','皇后','國王')
$cards = foreach ($page in $pages) {
    $info = $page.imageinfo[0]
    if ($info.extmetadata.LicenseShortName.value -ne 'Public domain') { throw "Review license: $($page.title)" }
    $originalName = $page.title -replace '^File:', ''
    if ($originalName -match '^RWS Tarot (\d+) (.+)\.jpg$') {
        $number = [int]$Matches[1]
        $nameEn = $Matches[2]
        $nameZh = $majorZh[$number]
        $id = 'major-{0:d2}' -f $number
        $arcana = 'major'; $suit = $null
    } elseif ($originalName -match '^(Cups|Pents|Swords|Wands)(\d+)\.jpg$') {
        $suit = @{ Cups='cups'; Pents='pentacles'; Swords='swords'; Wands='wands' }[$Matches[1]]
        $number = [int]$Matches[2]
        $nameEn = $ranksEn[$number-1] + ' of ' + (Get-Culture).TextInfo.ToTitleCase($suit)
        $nameZh = @{cups='聖杯';pentacles='錢幣';swords='寶劍';wands='權杖'}[$suit] + $ranksZh[$number-1]
        $id = '{0}-{1:d2}' -f $suit,$number
        $arcana = 'minor'
    } else { throw "Unrecognized: $originalName" }
    $file = Join-Path $destination "$id.jpg"
    if (!(Test-Path $file)) {
        $downloaded = $false
        for ($attempt=1; $attempt -le 4; $attempt++) {
            try {
                $downloadUrl = if ($info.thumburl) { $info.thumburl } else { $info.url }
                Invoke-WebRequest -Uri ($downloadUrl -replace '\?.*$', '') -OutFile "$file.part" -Headers @{'User-Agent'='TarotDeckSetup/1.0 (personal website assets)'}
                Move-Item -LiteralPath "$file.part" -Destination $file -Force
                $downloaded = $true
                break
            } catch { if ($attempt -eq 4) { throw }; Start-Sleep -Seconds (5*$attempt) }
        }
        Start-Sleep -Seconds 3
    }
    $bytes = [System.IO.File]::ReadAllBytes($file)
    if ($bytes.Length -lt 10000 -or $bytes[0] -ne 255 -or $bytes[1] -ne 216 -or $bytes[-2] -ne 255 -or $bytes[-1] -ne 217) { throw "Invalid JPEG: $file" }
    Write-Host "Verified $id"
    [ordered]@{id=$id; nameZh=$nameZh; nameEn=$nameEn; arcana=$arcana; suit=$suit; number=$number; image="/cards/rider-waite-smith/$id.jpg"; source=$info.descriptionurl; originalUrl=($info.url -replace '\?.*$',''); license=$info.extmetadata.LicenseShortName.value; artist='Pamela Colman Smith'; credit=$info.extmetadata.Credit.value; sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()}
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data') | Out-Null
ConvertTo-Json -InputObject @($cards) -Depth 5 | Set-Content (Join-Path $root 'data/cards.json') -Encoding utf8
Write-Host "Complete: $($cards.Count) cards"
