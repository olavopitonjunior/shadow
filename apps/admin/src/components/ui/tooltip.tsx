import * as React from "react"

import { cn } from "@/lib/utils"

interface TooltipProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "content"> {
  content: React.ReactNode
  side?: "top" | "right" | "bottom" | "left"
  children: React.ReactNode
}

const Tooltip = React.forwardRef<HTMLDivElement, TooltipProps>(
  ({ className, content, side = "top", children, ...props }, ref) => {
    const [visible, setVisible] = React.useState(false)

    const sideClasses = {
      top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
      right: "left-full top-1/2 -translate-y-1/2 ml-2",
      bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
      left: "right-full top-1/2 -translate-y-1/2 mr-2",
    }

    return (
      <div
        ref={ref}
        className={cn("relative inline-block", className)}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        {...props}
      >
        {children}
        {visible && (
          <div
            className={cn(
              "absolute z-50 px-3 py-1.5 text-sm text-white bg-gray-900 rounded-md shadow-md whitespace-nowrap pointer-events-none animate-in fade-in-0 zoom-in-95",
              sideClasses[side]
            )}
            role="tooltip"
          >
            {content}
            <div
              className={cn(
                "absolute w-2 h-2 bg-gray-900 transform rotate-45",
                side === "top" && "bottom-[-4px] left-1/2 -translate-x-1/2",
                side === "right" && "left-[-4px] top-1/2 -translate-y-1/2",
                side === "bottom" && "top-[-4px] left-1/2 -translate-x-1/2",
                side === "left" && "right-[-4px] top-1/2 -translate-y-1/2"
              )}
            />
          </div>
        )}
      </div>
    )
  }
)
Tooltip.displayName = "Tooltip"

const TooltipProvider = ({ children }: { children: React.ReactNode }) => {
  return <>{children}</>
}

const TooltipTrigger = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("cursor-pointer", className)} {...props} />
))
TooltipTrigger.displayName = "TooltipTrigger"

const TooltipContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "z-50 overflow-hidden rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md",
      className
    )}
    {...props}
  />
))
TooltipContent.displayName = "TooltipContent"

export { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent }
