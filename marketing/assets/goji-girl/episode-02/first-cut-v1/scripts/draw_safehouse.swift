import AppKit
import Foundation
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let H:CGFloat=1920
var svg=""
func col(_ hex:String,_ alpha:CGFloat=1)->NSColor {let n=UInt32(hex,radix:16)!;return NSColor(calibratedRed:CGFloat((n>>16)&255)/255,green:CGFloat((n>>8)&255)/255,blue:CGFloat(n&255)/255,alpha:alpha)}
func rect(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ h:CGFloat,_ c:String,_ a:CGFloat=1){col(c,a).setFill();NSRect(x:x,y:H-y-h,width:w,height:h).fill();svg+="<rect x='\(x)' y='\(y)' width='\(w)' height='\(h)' fill='#\(c)' opacity='\(a)'/>"}
func poly(_ points:[(CGFloat,CGFloat)],_ fill:String,_ stroke:String="",_ width:CGFloat=0){let p=NSBezierPath();p.move(to:NSPoint(x:points[0].0,y:H-points[0].1));for q in points.dropFirst(){p.line(to:NSPoint(x:q.0,y:H-q.1))};p.close();col(fill).setFill();p.fill();if !stroke.isEmpty{col(stroke).setStroke();p.lineWidth=width;p.lineJoinStyle = .round;p.stroke()};svg+="<polygon points='"+points.map{"\($0.0),\($0.1)"}.joined(separator:" ")+"' fill='#\(fill)' stroke='\(stroke.isEmpty ? "none" : "#"+stroke)' stroke-width='\(width)' stroke-linejoin='round'/>"}
func line(_ pts:[(CGFloat,CGFloat)],_ c:String,_ width:CGFloat){let p=NSBezierPath();p.move(to:NSPoint(x:pts[0].0,y:H-pts[0].1));for q in pts.dropFirst(){p.line(to:NSPoint(x:q.0,y:H-q.1))};p.lineWidth=width;p.lineJoinStyle = .round;col(c).setStroke();p.stroke();svg+="<polyline points='"+pts.map{"\($0.0),\($0.1)"}.joined(separator:" ")+"' fill='none' stroke='#\(c)' stroke-width='\(width)'/>"}
func text(_ s:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ c:String="ECEDE3",_ fontName:String="Arial-Black",_ outline:CGFloat=0){let f=NSFont(name:fontName,size:size) ?? NSFont.boldSystemFont(ofSize:size);let a:[NSAttributedString.Key:Any]=[.font:f,.foregroundColor:col(c)];if outline>0{let radius=outline/100*size;for (dx,dy) in [(-1.0,-1.0),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]{NSAttributedString(string:s,attributes:[.font:f,.foregroundColor:NSColor.black]).draw(at:NSPoint(x:x+CGFloat(dx)*radius,y:H-y-f.ascender+CGFloat(dy)*radius))}};NSAttributedString(string:s,attributes:a).draw(at:NSPoint(x:x,y:H-y-f.ascender));let safe=s.replacingOccurrences(of:"&",with:"&amp;").replacingOccurrences(of:"<",with:"&lt;");svg+="<text x='\(x)' y='\(y)' dominant-baseline='text-before-edge' font-family='\(fontName)' font-size='\(size)' fill='#\(c)' stroke='\(outline>0 ? "#000000" : "none")' stroke-width='\(outline/100*size)' paint-order='stroke fill'>\(safe)</text>"}
func render(_ name:String,_ draw:()->Void)throws{svg="<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='1920' viewBox='0 0 1080 1920'>";let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1080,pixelsHigh:1920,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!;let ctx=NSGraphicsContext(bitmapImageRep:rep)!;NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx;NSColor.clear.setFill();NSRect(x:0,y:0,width:1080,height:1920).fill(using:.copy);draw();ctx.flushGraphics();NSGraphicsContext.restoreGraphicsState();try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("overlays/\(name).png"));svg+="</svg>";try svg.write(to:root.appendingPathComponent("overlays/\(name).svg"),atomically:true,encoding:.utf8)}
try render("safehouse-popup"){
 rect(56,360,658,250,"142725",0.84)
 let lines=["You can save your game,","improve your stats, and","lose the police at a","safehouse."]
 for (i,s) in lines.enumerated(){text(s,80,379+CGFloat(i)*51,42,"E1E4D9","Arial-Black")}
}

try render("calendar-reminder"){
 rect(56,360,780,210,"142424",0.90)
 let lines=["CALENDAR","Goji Pilates","Appointment in 5 minutes"]
 for (i,s) in lines.enumerated(){text(s,82,386+CGFloat(i)*52,33,"E3E6D9","Arial-BoldMT")}
}
