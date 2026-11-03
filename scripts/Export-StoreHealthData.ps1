<#
.SYNOPSIS
    Read-only export of the store devices from Microsoft Intune (Microsoft Graph), optionally the domain-joined store computers from Active
    Directory and the Entra ID accounts of store staff, written as the CSV files that storehealth reads.

.DESCRIPTION
    Only read operations. Nothing is created, changed, synced, wiped or deleted, and no secret is written to disk.

    Microsoft Graph (Microsoft.Graph PowerShell SDK), delegated sign-in with read-only scopes:
      DeviceManagementManagedDevices.Read.All   managed devices (Get-MgDeviceManagementManagedDevice)
      User.Read.All                             only with -IncludeUsers: the store staff and shared store accounts (Get-MgUser)

      - devices.csv: one row per managed device (Windows store PCs, back-office PCs and laptops, Android handhelds and tablets) with
                     deviceName, operatingSystem, osVersion, lastSyncDateTime, model, manufacturer and serialNumber. store_id comes from the
                     device name with -StorePattern (a regular expression with a named group 'store'); role from the device name suffix with
                     -RoleBySuffix, or from deviceCategoryDisplayName when no suffix matches. source: Intune.
      - With -ADSearchBase (RSAT ActiveDirectory module, read-only Get-ADComputer): the domain-joined store computers under that OU with
                     OperatingSystem, OperatingSystemVersion ('10.0 (19045)') and LastLogonDate, added to devices.csv with source
                     'Active Directory' when Intune does not already have a device with the same name.
      - users.csv:   with -IncludeUsers, the accounts whose userPrincipalName matches -UserLike: userPrincipalName, displayName, employeeId,
                     accountEnabled, officeLocation (the store id) and createdDateTime.

    Not exported by this script (see docs/data-format.md for the columns of each one):
      - stores.csv       your store list (region, format, dates, field technician, hours, backup line);
      - connectivity.csv the daily export per store from your network monitoring tool (primary line availability, failovers and minutes on the
                         4G/LTE backup, last failover test, data used and cap of the backup SIM, site-to-site tunnel availability and drops,
                         failed AnyConnect connections);
      - printers.csv     the printer status and supplies your monitoring tool polls over SNMP (Host Resources MIB hrPrinterStatus and
                         hrPrinterDetectedErrorState, Printer MIB prtMarkerSuppliesLevel and prtMarkerSuppliesMaxCapacity);
      - card terminals and UPS rows for devices.csv, from the payment provider's portal and the UPS network cards;
      - tickets.csv      from your ITSM tool (ServiceNow list export or Jira CSV export);
      - openings.csv, staff.csv (HR joiners and leavers), and settings.json.

.PARAMETER OutputFolder
    Where the CSV files are written (default .\data).

.PARAMETER StorePattern
    Regular expression with a named group 'store' that finds the store id in the device name. Default: 'NW(?<store>\d{3})-' for names like
    NW001-PC01; the id is written as NW-001 (see -StorePrefix).

.PARAMETER StorePrefix
    Prefix added to the number captured by -StorePattern (default 'NW-').

.PARAMETER RoleBySuffix
    Hashtable from a device name suffix to a role (default PC = store PC, BO = back-office PC, LT = back-office laptop, HH = stock handheld,
    TB = tablet).

.PARAMETER ADSearchBase
    Distinguished name of the OU with the store computers in Active Directory. Without it, Active Directory is not read.

.PARAMETER IncludeUsers
    Export the store accounts from Entra ID to users.csv (User.Read.All).

.PARAMETER UserLike
    Wildcard for the userPrincipalName of the accounts to export (default '*').

.EXAMPLE
    .\scripts\Export-StoreHealthData.ps1 -OutputFolder .\data -IncludeUsers -UserLike '*@northwindoptics.example'

.EXAMPLE
    .\scripts\Export-StoreHealthData.ps1 -OutputFolder .\data -ADSearchBase 'OU=Stores,OU=Computers,DC=northwind,DC=local'
#>
[CmdletBinding()]
param(
    [string] $OutputFolder = '.\data',
    [string] $StorePattern = 'NW(?<store>\d{3})-',
    [string] $StorePrefix = 'NW-',
    [hashtable] $RoleBySuffix = @{ 'PC' = 'store PC'; 'BO' = 'back-office PC'; 'LT' = 'back-office laptop'; 'HH' = 'stock handheld'; 'TB' = 'tablet' },
    [string] $ADSearchBase,
    [switch] $IncludeUsers,
    [string] $UserLike = '*'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

function Write-Csv([object[]] $Rows, [string] $Name, [string[]] $Columns) {
    $path = Join-Path $OutputFolder $Name
    @($Rows) | Select-Object -Property $Columns | Export-Csv -Path $path -NoTypeInformation -Encoding utf8
    Write-Host ("{0,7} rows -> {1}" -f @($Rows).Count, $path)
}

function Format-Date($Value) {
    if (-not $Value) { return '' }
    return ([datetime] $Value).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

function Get-StoreId([string] $Name) {
    $m = [regex]::Match($Name, $StorePattern)
    if ($m.Success) { return $StorePrefix + $m.Groups['store'].Value }
    return ''
}

function Get-Role([string] $Name, [string] $Category) {
    foreach ($k in $RoleBySuffix.Keys) {
        if ($Name -match ("-{0}\d*$" -f [regex]::Escape($k))) { return $RoleBySuffix[$k] }
    }
    return $Category
}

# ---------------------------------------------------------------- Intune (Microsoft Graph)
Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.DeviceManagement
$scopes = @('DeviceManagementManagedDevices.Read.All')
if ($IncludeUsers) { $scopes += 'User.Read.All' }
Connect-MgGraph -Scopes $scopes -NoWelcome

$props = 'deviceName', 'operatingSystem', 'osVersion', 'lastSyncDateTime', 'model', 'manufacturer', 'serialNumber', 'deviceCategoryDisplayName'
$managed = Get-MgDeviceManagementManagedDevice -All -Property $props
$rows = foreach ($d in $managed) {
    [pscustomobject]@{
        deviceName       = $d.DeviceName
        operatingSystem  = $d.OperatingSystem
        osVersion        = $d.OsVersion
        lastSyncDateTime = Format-Date $d.LastSyncDateTime
        model            = $d.Model
        manufacturer     = $d.Manufacturer
        serialNumber     = $d.SerialNumber
        store_id         = Get-StoreId $d.DeviceName
        role             = Get-Role $d.DeviceName $d.DeviceCategoryDisplayName
        source           = 'Intune'
        health           = ''
        battery_date     = ''
    }
}
$rows = @($rows)
Write-Host ("{0} managed devices read from Intune" -f $rows.Count)

# ---------------------------------------------------------------- Active Directory (optional, read-only)
if ($ADSearchBase) {
    Import-Module ActiveDirectory
    $known = @{}
    foreach ($r in $rows) { $known[$r.deviceName.ToUpperInvariant()] = $true }
    $ad = Get-ADComputer -SearchBase $ADSearchBase -Filter 'Enabled -eq $true' -Properties OperatingSystem, OperatingSystemVersion, LastLogonDate
    $added = 0
    foreach ($c in $ad) {
        if ($known.ContainsKey($c.Name.ToUpperInvariant())) { continue }
        $rows += [pscustomobject]@{
            deviceName       = $c.Name
            operatingSystem  = $c.OperatingSystem
            osVersion        = $c.OperatingSystemVersion
            lastSyncDateTime = Format-Date $c.LastLogonDate
            model            = ''
            manufacturer     = ''
            serialNumber     = ''
            store_id         = Get-StoreId $c.Name
            role             = Get-Role $c.Name ''
            source           = 'Active Directory'
            health           = ''
            battery_date     = ''
        }
        $added++
    }
    Write-Host ("{0} domain-joined computers added from Active Directory (LastLogonDate replicates with a lag of up to 14 days)" -f $added)
}

$missing = @($rows | Where-Object { -not $_.store_id }).Count
if ($missing) { Write-Warning "$missing devices have no store_id: check -StorePattern or fill the column in." }
Write-Csv $rows 'devices.csv' @('deviceName', 'operatingSystem', 'osVersion', 'lastSyncDateTime', 'model', 'manufacturer', 'serialNumber', 'store_id',
    'role', 'source', 'health', 'battery_date')

# ---------------------------------------------------------------- Entra ID accounts (optional)
if ($IncludeUsers) {
    Import-Module Microsoft.Graph.Users
    $users = Get-MgUser -All -Property 'userPrincipalName', 'displayName', 'employeeId', 'accountEnabled', 'officeLocation', 'createdDateTime' |
        Where-Object { $_.UserPrincipalName -like $UserLike }
    $urows = foreach ($u in $users) {
        [pscustomobject]@{
            userPrincipalName = $u.UserPrincipalName
            displayName       = $u.DisplayName
            employeeId        = $u.EmployeeId
            accountEnabled    = $u.AccountEnabled
            officeLocation    = $u.OfficeLocation
            createdDateTime   = Format-Date $u.CreatedDateTime
        }
    }
    Write-Csv @($urows) 'users.csv' @('userPrincipalName', 'displayName', 'employeeId', 'accountEnabled', 'officeLocation', 'createdDateTime')
}

Disconnect-MgGraph | Out-Null
Write-Host "Done. Add stores.csv, connectivity.csv and printers.csv (monitoring tool), tickets.csv (ITSM), openings.csv, staff.csv (HR),"
Write-Host "the card terminal and UPS rows of devices.csv, check settings.json, then run: python -m storehealth review $OutputFolder"
