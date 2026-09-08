import { Alert, type AlertProps } from 'flowbite-react';

export function DashboardInfoBlock({
  color = 'info',
  rounded = true,
  className,
  children,
  ...props
}: AlertProps) {
  return (
    <Alert color={color} rounded={rounded} className={className} {...props}>
      {children}
    </Alert>
  );
}
