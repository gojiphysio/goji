import AppKit
import Foundation
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let H:CGFloat=1920
var svg=""
func col(_ hex:String,_ alpha:CGFloat=1)->NSColor {let n=UInt32(hex,radix:16)!;return NSColor(calibratedRed:CGFloat((n>>16)&255)/255,green:CGFloat((n>>8)&255)/255,blue:CGFloat(n&255)/255,alpha:alpha)}
func rect(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ h:CGFloat,_ c:String,_ a:CGFloat=1){col(c,a).setFill();NSRect(x:x,y:H-y-h,width:w,height:h).fill();svg+="<rect x='\(x)' y='\(y)' width='\(w)' height='\(h)' fill='#\(c)' opacity='\(a)'/>"}
func poly(_ points:[(CGFloat,CGFloat)],_ fill:String,_ stroke:String="",_ width:CGFloat=0){let p=NSBezierPath();p.move(to:NSPoint(x:points[0].0,y:H-points[0].1));for q in points.dropFirst(){p.line(to:NSPoint(x:q.0,y:H-q.1))};p.close();col(fill).setFill();p.fill();if !stroke.isEmpty{col(stroke).setStroke();p.lineWidth=width;p.lineJoinStyle = .round;p.stroke()};svg+="<polygon points='"+points.map{"\($0.0),\($0.1)"}.joined(separator:" ")+"' fill='#\(fill)' stroke='\(stroke.isEmpty ? "none" : "#"+stroke)' stroke-width='\(width)' stroke-linejoin='round'/>"}
func line(_ pts:[(CGFloat,CGFloat)],_ c:String,_ width:CGFloat){let p=NSBezierPath();p.move(to:NSPoint(x:pts[0].0,y:H-pts[0].1));for q in pts.dropFirst(){p.line(to:NSPoint(x:q.0,y:H-q.1))};p.lineWidth=width;p.lineJoinStyle = .round;col(c).setStroke();p.stroke();svg+="<polyline points='"+pts.map{"\($0.0),\($0.1)"}.joined(separator:" ")+"' fill='none' stroke='#\(c)' stroke-width='\(width)'/>"}
func text(_ s:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ c:String="ECEDE3",_ fontName:String="Arial-Black",_ outline:CGFloat=0){let f=NSFont(name:fontName,size:size) ?? NSFont.boldSystemFont(ofSize:size);var a:[NSAttributedString.Key:Any]=[.font:f,.foregroundColor:col(c)];if outline>0{let radius=outline/100*size;for (dx,dy) in [(-1.0,-1.0),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]{NSAttributedString(string:s,attributes:[.font:f,.foregroundColor:NSColor.black]).draw(at:NSPoint(x:x+CGFloat(dx)*radius,y:H-y-f.ascender+CGFloat(dy)*radius))}};NSAttributedString(string:s,attributes:a).draw(at:NSPoint(x:x,y:H-y-f.ascender));let safe=s.replacingOccurrences(of:"&",with:"&amp;").replacingOccurrences(of:"<",with:"&lt;");svg+="<text x='\(x)' y='\(y)' dominant-baseline='text-before-edge' font-family='\(fontName)' font-size='\(size)' fill='#\(c)' stroke='\(outline>0 ? "#000000" : "none")' stroke-width='\(outline/100*size)' paint-order='stroke fill'>\(safe)</text>"}
func render(_ name:String,_ draw:()->Void)throws{svg="<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='1920' viewBox='0 0 1080 1920'>";let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1080,pixelsHigh:1920,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!;let ctx=NSGraphicsContext(bitmapImageRep:rep)!;NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx;NSColor.clear.setFill();NSRect(x:0,y:0,width:1080,height:1920).fill(using:.copy);draw();ctx.flushGraphics();NSGraphicsContext.restoreGraphicsState();try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("overlays/\(name).png"));svg+="</svg>";try svg.write(to:root.appendingPathComponent("overlays/\(name).svg"),atomically:true,encoding:.utf8)}
func hud(_ clock:String){
 // Original vector handbag matching the player's black bag and gold clasp.
 rect(710,182,120,120,"050505");rect(718,190,104,104,"D9DED8")
 line([(748,233),(748,220),(752,210),(760,206),(772,206),(781,211),(785,220),(785,233)],"111111",7)
 poly([(738,230),(795,230),(805,282),(730,282)],"151515","050505",4)
 poly([(738,232),(795,232),(791,253),(744,253)],"272727","090909",2)
 rect(760,249,16,9,"C9A348");rect(763,251,10,4,"E5C56A")
 text(clock,849,190,49,"ECEDE3","Arial-Black",8)
 rect(846,261,183,28,"070707");rect(852,267,171,16,"A92B31")
 text("$00000350",719,307,47,"447D3D","Arial-Black",8)
 // Stylised local road layout; illustrative UI, not navigation.
 let map=NSBezierPath(ovalIn:NSRect(x:60,y:H-1420-210,width:240,height:210));NSGraphicsContext.saveGraphicsState();map.addClip();svg+="<defs><clipPath id='radar'><ellipse cx='180' cy='1525' rx='120' ry='105'/></clipPath></defs><g clip-path='url(#radar)'>"
 rect(60,1420,240,210,"869A72");rect(76,1431,72,60,"BEB8A4");rect(213,1435,76,73,"BCB6A1");rect(68,1564,78,66,"CCC5AA");rect(219,1565,70,63,"B5B299")
 for p in [[(95.0,1410.0),(161,1473),(167,1534),(202,1640)],[(42.0,1540.0),(146,1537),(213,1523),(320,1535)],[(211.0,1400.0),(207,1471),(231,1518),(285,1645)]] {line(p.map{(CGFloat($0.0),CGFloat($0.1))},"26312A",24);line(p.map{(CGFloat($0.0),CGFloat($0.1))},"E8E6D6",13)}
 line([(165,1545),(166,1494),(147,1457)],"E4CD54",5)
 poly([(174,1510),(160,1540),(174,1533),(188,1540)],"FAFAEF","111111",4)
 poly([(147,1443),(137,1455),(147,1470),(157,1455)],"E5D251","131510",3)
 NSGraphicsContext.restoreGraphicsState();svg+="</g>";col("080808").setStroke();map.lineWidth=9;map.stroke();svg+="<ellipse cx='180' cy='1525' rx='120' ry='105' fill='none' stroke='#080808' stroke-width='9'/>";text("N",277,1492,34,"FFFFFF","Arial-Black",12)
}
try render("gameplay-hud-0852"){hud("08:52")}
try render("gameplay-hud-0853"){hud("08:53")}
try render("body-muscle-popup"){
 rect(56,180,658,352,"142725",0.84)
 let lines=["Body Muscle -","Upgraded. You're","well-toned. Keep this","up and your attacks","will inflict more","damage."]
 for (i,s) in lines.enumerated(){text(s,80,199+CGFloat(i)*51,42,"E1E4D9","Arial-Black")}
}
print("Created editable SVG and transparent PNG overlay layers")

try render("mobility-popup"){
 rect(56,180,658,352,"142725",0.84)
 let lines=["Mobility -","Upgraded. You're","moving freely.","Keep this up to","improve your range","of motion."]
 for (i,s) in lines.enumerated(){text(s,80,199+CGFloat(i)*51,42,"E1E4D9","Arial-Black")}
}
