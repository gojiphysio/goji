import AppKit
import Foundation
let r=URL(fileURLWithPath:CommandLine.arguments[1])
for n in ["05","06","07","08","09"] {
 let w=1080,h=1920
 let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:w,pixelsHigh:h,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
 NSImage(contentsOf:r.appendingPathComponent("frames/"+n+"-look-clean.png"))!.draw(in:NSRect(x:0,y:0,width:w,height:h),from:.zero,operation:.copy,fraction:1)
 let path=NSBezierPath();let cx=842.0,cy=Double(h)-322.0
 for i in 0..<10 {let a=Double.pi/2+Double(i)*Double.pi/5;let radius=i%2==0 ? 32.0:14.0;let p=NSPoint(x:cx+cos(a)*radius,y:cy+sin(a)*radius);if i==0{path.move(to:p)}else{path.line(to:p)}}
 path.close();NSColor(calibratedRed:0.94,green:0.70,blue:0.10,alpha:1).setFill();path.fill();NSColor.black.setStroke();path.lineWidth=5;path.stroke()
 NSGraphicsContext.restoreGraphicsState();try rep.representation(using:.png,properties:[:])!.write(to:r.appendingPathComponent("frames/"+n+"-look.png"))
}
