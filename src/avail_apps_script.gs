/**
 * LPP2 availability backend. Paste into a new Google Apps Script project
 * (script.google.com), then Deploy > New deployment > Web app:
 *   Execute as: Me    Who has access: Anyone
 * Copy the /exec URL into src/config.json as "avail_url".
 *
 * Creates a sheet named "avail" in a spreadsheet bound to the script
 * (or set SHEET_ID to use an existing spreadsheet).
 */
var SHEET_ID = "";          // optional: paste a spreadsheet ID here
var SHEET_NAME = "avail";
var ALLOWED = ["aidan-roberts","isaiah-barnett","jake-vanderkar","matt-kostura","seth-king"];

function getSheet_() {
  var ss = SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) { ss = SpreadsheetApp.create("LPP2 availability"); SHEET_ID = ss.getId(); }
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) { sh = ss.insertSheet(SHEET_NAME); sh.appendRow(["week","player","status","at"]); }
  return sh;
}

function readAll_() {
  var sh = getSheet_();
  var vals = sh.getDataRange().getValues();
  var rows = [];
  for (var i = 1; i < vals.length; i++) {
    if (!vals[i][0]) continue;
    rows.push({week: String(vals[i][0]), player: String(vals[i][1]), status: String(vals[i][2]||""), at: String(vals[i][3]||"")});
  }
  return rows;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  return json_({ok: true, rows: readAll_()});
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var body = JSON.parse(e.postData.contents || "{}");
    var week = String(body.week || ""), player = String(body.player || "");
    var status = String(body.status || ""), at = String(body.at || new Date().toISOString());
    if (!/^w\d{4}-\d{2}-\d{2}$/.test(week)) return json_({ok:false, error:"bad week"});
    if (ALLOWED.indexOf(player) < 0) return json_({ok:false, error:"unknown player"});
    if (["", "yes", "maybe", "no"].indexOf(status) < 0) return json_({ok:false, error:"bad status"});
    var sh = getSheet_();
    var vals = sh.getDataRange().getValues();
    for (var i = 1; i < vals.length; i++) {
      if (String(vals[i][0]) === week && String(vals[i][1]) === player) {
        sh.getRange(i + 1, 3, 1, 2).setValues([[status, at]]);
        return json_({ok: true, updated: true});
      }
    }
    sh.appendRow([week, player, status, at]);
    return json_({ok: true, created: true});
  } catch (err) {
    return json_({ok:false, error: String(err)});
  } finally {
    lock.releaseLock();
  }
}
