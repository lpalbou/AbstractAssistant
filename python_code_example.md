# Python Code Examples

## Basic Python Script
```python
# Hello World program
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
```

## Data Processing with Pandas
```python
import pandas as pd
import numpy as np

# Create a sample dataset
data = {
    'name': ['Alice', 'Bob', 'Charlie', 'Diana'],
    'age': [25, 30, 35, 28],
    'city': ['New York', 'London', 'Tokyo', 'Paris']
}
df = pd.DataFrame(data)

# Display basic statistics
print("Dataset summary:")
print(df.describe())

# Filter data
young_people = df[df['age'] < 30]
print("\nPeople under 30:")
print(young_people)
```

## Function with Error Handling
```python
def divide_numbers(a, b):
    """
    Divide two numbers with proper error handling
    """
    try:
        result = a / b
        return result
    except ZeroDivisionError:
        print("Error: Cannot divide by zero!")
        return None
    except TypeError:
        print("Error: Please provide numeric values!")
        return None

# Test the function
print(divide_numbers(10, 2))   # Output: 5.0
print(divide_numbers(10, 0))   # Error message
print(divide_numbers("10", 2)) # Error message
```

## File Operations
```python
# Reading and writing files
def write_to_file(filename, content):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Content written to {filename}")

def read_from_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"File {filename} not found")
        return None

# Example usage
write_to_file("sample.txt", "This is a sample text file.")
content = read_from_file("sample.txt")
print(f"File content: {content}")
```

## List Comprehensions and Lambda Functions
```python
# List comprehension examples
numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# Even numbers using list comprehension
evens = [x for x in numbers if x % 2 == 0]
print(f"Even numbers: {evens}")

# Squares using list comprehension
squares = [x**2 for x in numbers]
print(f"Squares: {squares}")

# Lambda functions
multiply = lambda x, y: x * y
print(f"5 * 7 = {multiply(5, 7)}")

# Using lambda with map
squared = list(map(lambda x: x**2, numbers))
print(f"Squared using map: {squared}")
```

> This document contains examples of basic Python programming concepts including functions, data processing with pandas, error handling, file operations, and list comprehensions.