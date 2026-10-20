#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int[]]$Ports = @(5173, 4173)
)

$ErrorActionPreference = 'Stop'
$nodeExecutable = (Get-Command node -CommandType Application -ErrorAction Stop).Source
foreach ($port in $Ports) {
    $ruleName = "NTECH-EMS-LAN-$port"
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($rule) {
        $rule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any
        $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $port
        $rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet
        $rule | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter -Program $nodeExecutable
    } else {
        New-NetFirewallRule -Name $ruleName -DisplayName "NTECH EMS LAN ($port)" `
            -Direction Inbound -Action Allow -Enabled True -Profile Any `
            -Protocol TCP -LocalPort $port -RemoteAddress LocalSubnet -Program $nodeExecutable | Out-Null
    }
    Write-Output "Allowed NTECH EMS on TCP $port from the local subnet."
}
