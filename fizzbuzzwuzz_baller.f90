program fizzbuzzwuzz_baller
  implicit none
  ! Variables for parsing
  integer :: i, nargs, arg_len, status
  integer :: start_val, end_val
  integer, allocatable :: divisors(:)
  character(len=:), allocatable :: words(:)
  character(len=100) :: arg
  character(len=32) :: out
  integer :: ndiv, j
  logical :: help_requested
  integer :: new_divisor
  character(len=100) :: new_word

  ! Defaults
  start_val = 1
  end_val = 100
  ndiv = 0
  help_requested = .false.

  nargs = command_argument_count()
  i = 1
  do while (i <= nargs)
    call get_command_argument(i, arg, length=arg_len, status=status)
    if (status /= 0) then
      i = i + 1
      cycle
    end if
    select case (trim(arg))
    case ('--help', '-h')
      help_requested = .true.
    case ('--start')
      i = i + 1
      call get_command_argument(i, arg, length=arg_len, status=status)
      if (status == 0) then
        read(arg,*,iostat=status) start_val
        if (status /= 0) then
          print *, 'Error: invalid start value'
          stop 1
        end if
      end if
    case ('--end')
      i = i + 1
      call get_command_argument(i, arg, length=arg_len, status=status)
      if (status == 0) then
        read(arg,*,iostat=status) end_val
        if (status /= 0) then
          print *, 'Error: invalid end value'
          stop 1
        end if
      end if
    case ('--div')
      i = i + 1
      call get_command_argument(i, arg, length=arg_len, status=status)
      if (status == 0) then
        read(arg,*,iostat=status) new_divisor
        if (status /= 0) then
          print *, 'Error: invalid divisor'
          stop 1
        end if
        i = i + 1
        call get_command_argument(i, arg, length=arg_len, status=status)
        if (status /= 0) then
          print *, 'Error: missing word for divisor'
          stop 1
        end if
        new_word = trim(arg)
        ! Expand arrays
        ndiv = ndiv + 1
        if (allocated(divisors)) then
          divisors = [divisors, new_divisor]
          words = [words, new_word]
        else
          allocate(divisors(1), words(1))
          divisors(1) = new_divisor
          words(1) = new_word
        end if
      else
        print *, 'Error: missing divisor value'
        stop 1
      end if
    case default
      ! Ignore unknown arguments
    end select
    i = i + 1
  end do

  if (help_requested) then
    print *, 'Usage: fizzbuzzwuzz_baller [options]'
    print *, 'Options:'
    print *, '  --start N   Set start number (default 1)'
    print *, '  --end N     Set end number (default 100)'
    print *, '  --div D W   Add divisor D and corresponding word W'
    print *, '  --help, -h  Show this help'
    print *, 'If no --div options are given, default is: 3 Fizz, 5 Buzz, 7 Wuzz'
    stop
  end if

  ! If no divisors specified, set default
  if (ndiv == 0) then
    ndiv = 3
    allocate(divisors(ndiv))
    allocate(words(ndiv))
    divisors = [3, 5, 7]
    words = ['Fizz', 'Buzz', 'Wuzz']
  end if

  ! Main loop
  do i = start_val, end_val
    out = ''
    do j = 1, ndiv
      if (mod(i, divisors(j)) == 0) then
        out = trim(out) // words(j)
      end if
    end do
    if (len_trim(out) == 0) then
      print '(I0)', i
    else
      print '(A)', trim(out)
    end if
  end do

end program fizzbuzzwuzz_baller