# Confere o endereço padrão do instalador de release (ADR-027) antes do ISCC. Mesma regra do
# EnderecoValido() do .iss e de servicos/api.py validar(): https://, host, sem usuário, senha,
# query, fragmento, espaço ou barra invertida; e sem aspas (o valor entra numa string do Pascal).
# Nunca imprime o valor, o tamanho nem parte dele. Sai 0 se válido, 1 se ausente ou inválido.
param([string]$Endereco = $env:BENCH_API_URL)
$e = "$Endereco".Trim()
$ok = $e -match '^(?i)https://' -and $e -notmatch '[\x00-\x20@?#\\''"]'
if ($ok) {
    $resto = $e.Substring(8)
    $hostPart = ($resto -split '/', 2)[0]
    $ok = $hostPart -ne '' -and -not $hostPart.StartsWith(':')
}
if (-not $ok) {
    Write-Host '::error::BENCH_API_URL ausente ou inválido (https:// com host, sem usuário, senha, query nem fragmento).'
    exit 1
}
exit 0
