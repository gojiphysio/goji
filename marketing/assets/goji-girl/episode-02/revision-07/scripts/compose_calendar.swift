import AppKit
import Foundation
let r=URL(fileURLWithPath:CommandLine.arguments[1]);let w=1080,h=1920
let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:w,pixelsHigh:h,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
let img=NSImage(contentsOf:r.appendingPathComponent("frames/02-look-clean.png"))!
img.draw(in:NSRect(x:0,y:0,width:w,height:h),from:.zero,operation:.copy,fraction:1)
NSColor(calibratedRed:0.08,green:0.14,blue:0.14,alpha:0.90).setFill()
NSRect(x:56,y:h-360-210,width:780,height:210).fill()
let lines:[(String,CGFloat,Int)]=[("CALENDAR",24,386),("Goji Pilates",43,426),("Appointment in 5 minutes",33,489)]
for (s,size,y) in lines {
 NSAttributedString(string:s,attributes:[.font:NSFont(name:"Arial-BoldMT",size:size)!, .foregroundColor:NSColor(calibratedRed:0.89,green:0.90,blue:0.85,alpha:1)]).draw(at:NSPoint(x:82,y:CGFloat(h-y)-size*1.15))
}
NSGraphicsContext.restoreGraphicsState()
try rep.representation(using:.png,properties:[:])!.write(to:r.appendingPathComponent("frames/02-look.png"))

