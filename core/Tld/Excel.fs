module Tld.Excel

// Writing a Tld.Workbooks workbook to .xlsx bytes, and reading the active sheet
// of an uploaded .xlsx, through exceljs. In memory both ways: nothing here
// touches the network, a file or the clock. The shell only turns the bytes
// into a download (lib/tld/workbook.js).
//
// The one module in core that imports a package. exceljs is bound loosely, by
// the few members used, rather than through a full binding, because the
// surface is small and a binding is a second thing to keep current.

open Fable.Core
open Fable.Core.JsInterop

(*=======================================================
        THE INTEROP SEAM, AND ALL OF IT IS HERE
========================================================*)

[<Import("default", "exceljs")>]
let private ExcelJS: obj = jsNative

[<Emit("new $0.Workbook()")>]
let private newWorkbook (lib: obj) : obj = jsNative

[<Emit("($0 instanceof Date)")>]
let private isDate (value: obj) : bool = jsNative

[<Emit("(typeof $0 === 'object' && $0 !== null)")>]
let private isObjectValue (value: obj) : bool = jsNative

[<Emit("($1 in $0)")>]
let private has (value: obj) (key: string) : bool = jsNative

[<Emit("String($0)")>]
let private str (value: obj) : string = jsNative

// Plain property assignment. F#'s dynamic `x?prop <- v` on a method's result
// compiles to a reference to an undefined copyOfStruct under Fable 5.22.
[<Emit("$0[$1] = $2")>]
let private setField (target: obj) (key: string) (value: obj) : unit = jsNative

// One cell's value. Spelled out because a chained ?getRow(r)?getCell(c)?value
// parses as getRow(r.getCell, ...), passing the wrong thing to the wrong call.
[<Emit("$0.getRow($1).getCell($2).value")>]
let private cellValue (sheet: obj) (row: int) (column: int) : obj = jsNative

// The tab Excel had open when the file was saved, which openpyxl's .active read
[<Emit("($0.views && $0.views[0] && $0.views[0].activeTab) || 0")>]
let private activeTab (workbook: obj) : int = jsNative

(*=======================================================
        WRITING
========================================================*)

(*
 Plain cells, as openpyxl's Workbook() wrote them. An empty row is an empty
 row, as ws.append([]) left one. The only formatting is the text column and
 the widths a Tld.Workbooks sheet asks for.
*)
let write (book: obj) : JS.Promise<obj> =
    let wb = newWorkbook ExcelJS
    for sheet in unbox<Workbooks.Sheet array> (book?sheets) do
        let ws = wb?addWorksheet (sheet.name)
        sheet.rows
        |> Array.iteri (fun i cells ->
            let row = ws?getRow (i + 1)
            cells
            |> Array.iteri (fun j value -> if not (isNull value) then setField (row?getCell (j + 1)) "value" value)
            row?commit () |> ignore)
        if sheet.textColumn > 0 then
            for r in sheet.fromRow .. sheet.rows.Length do
                setField (ws?getCell (r, sheet.textColumn)) "numFmt" "@"
        sheet.widths |> Array.iteri (fun i width -> setField (ws?getColumn (i + 1)) "width" width)
    wb?xlsx?writeBuffer ()

(*=======================================================
        READING
========================================================*)

// What a cell holds, as openpyxl's data_only read gave it: a formula's result, a link's text
let rec private plain (value: obj) : obj =
    if isNull value then box ""
    elif isDate value || not (isObjectValue value) then value
    elif has value "result" then plain (value?result)
    elif has value "richText" then
        box (unbox<obj array> (value?richText) |> Array.map (fun part -> str (part?text)) |> String.concat "")
    elif has value "text" then plain (value?text)
    elif has value "error" then box ""
    else box (str value)

(*
 The active sheet as { header, records }, the shape Tld.Csv.read gives a CSV:
 the first row's text is the header, every later row an object keyed by it.
 Dates stay Dates; exceljs puts Excel's wall time in their UTC fields, which
 is how Tld.TransferCheck.parseTime reads them.
*)
let read (bytes: obj) : JS.Promise<obj> =
    let wb = newWorkbook ExcelJS
    let loaded: JS.Promise<obj> = wb?xlsx?load (bytes)
    loaded.``then`` (fun _ ->
        let sheets = unbox<obj array> (wb?worksheets)
        let active = activeTab wb
        let ws = if active < sheets.Length then sheets.[active] elif sheets.Length > 0 then sheets.[0] else null
        if isNull ws then box {| header = [||]; records = [||] |}
        else
            let columns = unbox<int> (ws?columnCount)
            let cellsOf (r: int) = Array.init columns (fun c -> plain (cellValue ws r (c + 1)))
            let header = cellsOf 1 |> Array.map (fun h -> (str h).Trim())
            let records =
                [| for r in 2 .. unbox<int> (ws?rowCount) do
                       let values = cellsOf r
                       yield createObj (header |> Array.mapi (fun i h -> h, (if i < values.Length then values.[i] else box ""))) |]
            box {| header = header; records = records |})
