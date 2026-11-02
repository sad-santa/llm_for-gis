$ErrorActionPreference = "Stop"

$projectDir = $PSScriptRoot
$inputDir = Join-Path $projectDir "input"
$outputDir = Join-Path $projectDir "output"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
Set-Location -LiteralPath $projectDir

uv run metadata-extractor extract `
    (Join-Path $inputDir "новая карта_n5420_gk_1.jpg") `
    --output-dir $outputDir `
    --keep-intermediate

uv run metadata-extractor extract `
    (Join-Path $inputDir "Приложение 9.pdf") `
    --output-dir $outputDir `
    --keep-intermediate

uv run metadata-extractor extract `
    (Join-Path $inputDir "Прогнозная_карта_27_06.pdf") `
    --output-dir $outputDir `
    --keep-intermediate
