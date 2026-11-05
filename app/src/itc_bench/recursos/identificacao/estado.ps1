# Nome ativo e pendente, domínio/Azure AD e nomes locais (ADR-018). Só leitura; devolve JSON.
$cs = Get-CimInstance -ClassName Win32_ComputerSystem
$base = 'HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName'
$join = 'HKLM:\SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo'
[pscustomobject]@{
    ativo    = (Get-ItemProperty "$base\ActiveComputerName").ComputerName
    pendente = (Get-ItemProperty "$base\ComputerName").ComputerName
    dominio  = [bool]$cs.PartOfDomain
    azuread  = (@(Get-ChildItem $join -ErrorAction SilentlyContinue).Count -gt 0)
    nomes    = @(@(Get-LocalUser | ForEach-Object { $_.Name }) + @(Get-LocalGroup | ForEach-Object { $_.Name }))
} | ConvertTo-Json -Compress
