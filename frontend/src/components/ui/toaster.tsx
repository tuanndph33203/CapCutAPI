import React from "react";
import { Toaster as Sonner } from "sonner";
import "sonner/dist/styles.css";

type ToasterProps = React.ComponentProps<typeof Sonner>;

export const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      position="top-right"
      richColors
      closeButton
      style={{ zIndex: 999999 }}
      toastOptions={{
        style: {
          zIndex: 999999,
          background: "#18181b",
          color: "#ffffff",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          borderRadius: "0.75rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)",
          backdropFilter: "blur(12px)",
          padding: "12px 16px",
          fontSize: "14px",
        },
      }}
      {...props}
    />
  );
};
