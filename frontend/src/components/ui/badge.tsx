import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold tracking-wide uppercase transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-cyan-500/30 bg-cyan-500/10 text-cyan-300 shadow-sm shadow-cyan-500/10",
        secondary:
          "border-white/10 bg-secondary text-secondary-foreground",
        success:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
        destructive:
          "border-red-500/30 bg-red-500/10 text-red-400",
        warning:
          "border-amber-500/30 bg-amber-500/10 text-amber-300",
        outline: "border-white/20 text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
