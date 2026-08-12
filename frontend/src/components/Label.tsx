/** A form label that marks required fields with a red star. */
export function Label({
  htmlFor,
  children,
  required = false,
}: {
  htmlFor: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label htmlFor={htmlFor}>
      {children}
      {required && (
        <span className="req" aria-hidden="true" title="Required">
          *
        </span>
      )}
    </label>
  );
}
