/** Form renderer using react-hook-form and zod. */
import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

interface FormRendererProps {
  schema: z.ZodObject<any>;
  onSubmit: (data: any) => void;
  fields: Array<{
    name: string;
    label: string;
    type: 'text' | 'number' | 'email' | 'select';
    options?: Array<{ value: string; label: string }>;
  }>;
}

const FormRenderer: React.FC<FormRendererProps> = ({ schema, onSubmit, fields }) => {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="form-renderer">
      {fields.map((field) => (
        <div key={field.name} className="form-field">
          <label htmlFor={field.name}>{field.label}</label>
          {field.type === 'select' ? (
            <select {...register(field.name)}>
              {field.options?.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={field.type}
              {...register(field.name)}
              id={field.name}
            />
          )}
          {errors[field.name] && (
            <span className="form-error">
              {errors[field.name]?.message as string}
            </span>
          )}
        </div>
      ))}
      <button type="submit">Submit</button>
    </form>
  );
};

export default FormRenderer;


