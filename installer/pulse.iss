; Inno Setup script for PULSE (spec §11).
; Build with Inno Setup 6 (https://jrsoftware.org/isdl.php):
;   ISCC.exe installer\pulse.iss /DMyAppVersion=1.0.0
;
; This installs to the user's local programs folder — no administrator
; rights required. Data (SQLite database, config.yaml) stays in
; %LOCALAPPDATA%\PULSE\ and is NOT touched by uninstall.

#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif

#define MyAppName    "PULSE"
#define MyAppExeName "PULSE.exe"
#define MyAppPublisher "Divergent Futures / Humans in Space"
#define MyAppURL  "https://github.com/space-divergentfutures/pulse"

[Setup]
AppId={{6E1A9F4B-3D2C-4E8F-B7A1-0F5C2D9E3A84}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Per-user install — no elevation needed, installs to %LOCALAPPDATA%\Programs\
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=.
OutputBaseFilename=PULSE-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Data directory is outside the app directory — never deleted on uninstall.
; (storage.py uses %LOCALAPPDATA%\PULSE\pulse.db by default)

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire one-dir PyInstaller output
Source: "..\dist\PULSE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// WebView2 Runtime check — required by pywebview (spec §11).
// The Evergreen Runtime ships with Windows 11 and modern Edge.
// If absent, we offer the official Microsoft bootstrapper download page.

const
  WV2_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function IsWebView2Installed: Boolean;
var
  Dummy: String;
begin
  Result :=
    RegQueryStringValue(HKLM,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2_GUID,
      'pv', Dummy) or
    RegQueryStringValue(HKLM,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2_GUID,
      'pv', Dummy) or
    RegQueryStringValue(HKCU,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2_GUID,
      'pv', Dummy);
end;

procedure InitializeWizard;
begin
  // Nothing extra needed here — check happens at FinishInstall time.
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not IsWebView2Installed then
    begin
      if MsgBox(
        'PULSE needs the Microsoft WebView2 Runtime to display its interface.' + #13#10 +
        'It ships with Windows 11 and modern versions of Edge.' + #13#10 + #13#10 +
        'Would you like to open the WebView2 download page now?' + #13#10 +
        '(Free, takes under a minute to install.)',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        ShellExec('open',
          'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
          '', '', SW_SHOWNORMAL, ewNoWait, Dummy);
      end;
    end;
  end;
end;
