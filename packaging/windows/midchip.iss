; inno setup script for MidChip.
; Build with: iscc packaging\windows\midchip.iss
; (requires Inno Setup 6: https://jrsoftware.org/isinfo.php)
;
; note: you need to build the app first (script/build.bat) before building this!

#define MyAppName "MidChip"
#ifndef MyAppVersion
  #define MyAppVersion "2.3.0"
#endif
#define MyAppPublisher "turtledevv"
#define MyAppURL "https://github.com/turtledevv/midchip"
#define MyAppExeName "midchip-gui.exe"
#define SourceDist "..\..\dist\midchip"

[Setup]
AppId={{7C6C1E2B-6C0F-4E31-9E9C-6D6F6964636870}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; installs to Program Files\MidChip (64-bit path on 64-bit Windows).
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; per-machine install (needs elevation) so it lands in Program Files
; for all users, matching normal Windows app conventions.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=midchip-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "addtopath"; Description: "Add MidChip to PATH (for midchip / midchip-viz in a terminal)"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; everything pyinstaller produced
Source: "{#SourceDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut -> midchip-gui.exe
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; optional desktop shortcut -> midchip-gui.exe
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
