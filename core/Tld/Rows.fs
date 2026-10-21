module Tld.Rows

// Reading TLD's rows. Every row the egress api returns is a loose JSON object
// whose values arrive as strings, numbers or null depending on the column and
// the day, so nothing downstream reads a field any way but through here.
//
// Shared by every TLD module, not only the dashboard. Ported from the TLD
// dashboard's tldcrm_client.py (_num, _first_num, the str(x or "").strip()
// idiom). The rules are Python's, kept exactly, because the numbers on the
// page were reconciled against TLD under them.

open Fable.Core

(*=======================================================
        THE INTEROP SEAM, AND ALL OF IT IS HERE
========================================================*)

(*
 A row is a plain object read by key. Bound as Emit rather than through a
 typed interface because the columns differ per endpoint and per query, and
 a type per query would be a second copy of the column lists that drifts.
*)
type Row = obj

// null, never undefined, for a missing field, as Python's row.get() gives None: undefined drops the key from the JSON
[<Emit("($0 == null ? null : ($0[$1] ?? null))")>]
let get (row: Row) (key: string) : obj = jsNative

// JavaScript truthiness matches Python's for every value TLD sends: null, "", 0 and false
[<Emit("!!$0")>]
let private truthy (value: obj) : bool = jsNative

[<Emit("String($0)")>]
let private toText (value: obj) : string = jsNative

[<Emit("Number($0)")>]
let private toNumber (value: obj) : float = jsNative

[<Emit("($0 !== null && typeof $0 === 'object' && !Array.isArray($0))")>]
let isObject (value: obj) : bool = jsNative

[<Emit("Array.isArray($0)")>]
let isArray (value: obj) : bool = jsNative

[<Emit("Object.values($0)")>]
let private values (row: Row) : obj array = jsNative

[<Emit("Object.keys($0)")>]
let keys (row: Row) : string array = jsNative

// Python's str(value) inside an f-string: None reads "None", where the dashboard printed it
[<Emit("($0 == null ? 'None' : String($0))")>]
let pyStr (value: obj) : string = jsNative

// The exact decimal digits of a float, which toFixed gives for up to 100 places
[<Emit("$1.toFixed($0)")>]
let private fixedDigits (places: int) (value: float) : string = jsNative

(*=======================================================
        FIELDS
========================================================*)

// Python's str(row.get(key) or "").strip(): absent, null, empty and 0 all read as ""
let text (row: Row) (key: string) : string =
    let value = get row key
    if truthy value then (toText value).Trim() else ""

// The same rule for a value already in hand
let textOf (value: obj) : string =
    if truthy value then (toText value).Trim() else ""

// Python's str(value or "") without the strip, where a sort compared the raw text
let rawText (value: obj) : string =
    if truthy value then toText value else ""

// Python's `a or b`: the value itself when it is truthy, else the fallback
let orElse (fallback: obj) (value: obj) : obj = if truthy value then value else fallback

(*-------- This is critical --------*)
(*
 Python's round(x, places). Not toFixed alone: on a value that is exactly half
 way, Python rounds to the even digit and toFixed rounds up, so 33.25 is 33.2
 in Python and 33.3 here, and Conversion Rate would differ by a tenth on the
 days that happens. Ties are only real when every digit past the cut is 0
 after a 5, which the long expansion below shows exactly; anything else is
 not a tie and toFixed is already the nearest.
*)
let pyRound (places: int) (value: float) : float =
    if System.Double.IsNaN value || System.Double.IsInfinity value then value
    else
        let exact = fixedDigits (places + 60) (abs value)
        let cut = exact.IndexOf('.') + 1 + places
        let tail = exact.Substring(cut)
        let isTie = tail.[0] = '5' && tail.Substring(1) |> Seq.forall (fun c -> c = '0')
        let rounded =
            if not isTie then float (fixedDigits places (abs value))
            else
                let kept = exact.Substring(0, cut).TrimEnd('.')
                let lastDigit = int kept.[kept.Length - 1] - int '0'
                let down = float kept
                if lastDigit % 2 = 0 then down
                else float (fixedDigits places (down + 10.0 ** float -places))
        if value < 0.0 then -rounded else rounded

// Money to the cent, as Python's round(x, 2)
let round2 (value: float) : float = pyRound 2 value

(*
 Python's _num. Anything that does not parse is 0, never NaN, because a NaN in
 one row poisons every sum it reaches and the page shows nothing at all.
*)
let numOf (value: obj) : float =
    if isNull value then 0.0
    else
        let n = toNumber value
        if System.Double.IsNaN n || System.Double.IsInfinity n then 0.0 else n

let num (row: Row) (key: string) : float = numOf (get row key)

// Python's _first_num. The first non zero value in the first row, for aggregate queries
let firstNum (rows: Row array) : float =
    if Array.isEmpty rows then 0.0
    else
        let first = rows.[0]
        if isObject first then
            values first
            |> Array.tryPick (fun v ->
                let n = numOf v
                if n <> 0.0 then Some n else None)
            |> Option.defaultValue 0.0
        else
            numOf first

(*
 The other unwrap: peel "response", then "results", and stop there, whatever
 is inside. Reports answer as results: { records: [...], totals: {...} }, and
 the totals are lost if this unwraps any further. The Python's config.unwrap.
*)
let unwrapResults (payload: obj) : obj =
    if isObject payload then
        let inner = if isNull (get payload "response") then payload else get payload "response"
        if isObject inner && not (isNull (get inner "results")) then get inner "results" else inner
    else
        payload

(*
 TLD wraps results as {"response": {"results": [...]}}, sometimes flatter. The
 unwrap the dashboard has always used, kept so an endpoint that answers in an
 odd shape behaves the same as it did.
*)
let unwrap (payload: obj) : Row array =
    let inner =
        if isObject payload && isObject (get payload "response") then get payload "response"
        else payload

    if isArray inner then
        (unbox<obj array> inner) |> Array.filter isObject
    elif isObject inner then
        [ "results"; "data"; "rows" ]
        |> List.tryPick (fun key ->
            let v = get inner key
            if isArray v then Some((unbox<obj array> v) |> Array.filter isObject) else None)
        |> Option.defaultValue [| inner |]
    else
        [||]
