'use client'

import React, { useState, useRef, useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { Star, Leaf, ChevronDown, Search, X, Zap } from 'lucide-react'
import type { Supplier } from '@/types'

interface SupplierSelectorProps {
  suppliers: Supplier[]
  value: Supplier | null
  onChange: (supplier: Supplier | null) => void
  placeholder?: string
  disabled?: boolean
}

export const SupplierSelector: React.FC<SupplierSelectorProps> = ({
  suppliers,
  value,
  onChange,
  placeholder = 'Select a supplier...',
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  const filtered = suppliers.filter((s) =>
    s.name.toLowerCase().includes(search.toLowerCase())
  )

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Selected value / trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-left transition-colors hover:border-gray-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {value ? (
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary-500" />
            <span className="font-medium text-gray-900">{value.name}</span>
            {value.greenEnergy && (
              <Leaf className="h-3.5 w-3.5 text-success-500" />
            )}
          </div>
        ) : (
          <span className="text-gray-400">{placeholder}</span>
        )}
        <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg">
          {/* Search */}
          <div className="border-b border-gray-100 p-2">
            <div className="flex items-center gap-2 rounded-md border border-gray-200 px-2 py-1.5">
              <Search className="h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search suppliers..."
                className="w-full bg-transparent text-sm outline-none placeholder:text-gray-400"
                autoFocus
              />
              {search && (
                <button onClick={() => setSearch('')}>
                  <X className="h-3 w-3 text-gray-400" />
                </button>
              )}
            </div>
          </div>

          {/* Options */}
          <div className="max-h-60 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-sm text-gray-500">No suppliers found</p>
            ) : (
              filtered.map((supplier) => (
                <button
                  key={supplier.id}
                  type="button"
                  onClick={() => {
                    onChange(supplier)
                    setIsOpen(false)
                    setSearch('')
                  }}
                  className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                    value?.id === supplier.id
                      ? 'bg-primary-50 text-primary-700'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{supplier.name}</span>
                    {supplier.greenEnergy && (
                      <Badge variant="success" size="sm">
                        <Leaf className="mr-1 h-3 w-3" />
                        Green
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1 text-gray-400">
                    <Star className="h-3 w-3 fill-warning-400 text-warning-400" />
                    <span className="text-xs">{supplier.rating}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
